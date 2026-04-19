"""Backward-compatibility shim. Import ErrorHistoryMiddleware from error_history_middleware instead."""

import warnings

warnings.warn(
    "apcore.middleware.error_history is deprecated; use apcore.middleware.error_history_middleware",
    DeprecationWarning,
    stacklevel=2,
)

from apcore.middleware.error_history_middleware import ErrorHistoryMiddleware  # noqa: F401, E402
