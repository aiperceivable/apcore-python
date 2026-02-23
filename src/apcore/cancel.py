"""Cooperative cancellation support for apcore module execution."""

from __future__ import annotations


class ExecutionCancelledError(Exception):
    """Raised when a module execution is cancelled via CancelToken."""

    def __init__(self, message: str = "Execution was cancelled") -> None:
        super().__init__(message)


class CancelToken:
    """Cooperative cancellation token for module execution.

    Pass to Context and check periodically during long-running operations.
    """

    def __init__(self) -> None:
        self._cancelled: bool = False

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._cancelled

    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True

    def check(self) -> None:
        """Raise ExecutionCancelledError if cancelled.

        Call this periodically in long-running operations.
        """
        if self._cancelled:
            raise ExecutionCancelledError()

    def reset(self) -> None:
        """Reset the token for reuse."""
        self._cancelled = False
