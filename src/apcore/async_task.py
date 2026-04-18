"""Async task manager for background module execution."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from apcore.context import Context
from apcore.errors import TaskLimitExceededError

__all__ = ["TaskStatus", "TaskInfo", "AsyncTaskManager", "ExecutorProtocol"]


@runtime_checkable
class ExecutorProtocol(Protocol):
    """Minimal async-call surface required by :class:`AsyncTaskManager`.

    Provided as a ``Protocol`` so tests can inject a lightweight fake
    without constructing a full :class:`apcore.executor.Executor`. The
    concrete ``Executor`` satisfies this protocol via ``call_async``.
    """

    async def call_async(
        self,
        module_id: str,
        inputs: dict[str, Any] | None = None,
        context: Context | None = None,
        version_hint: str | None = None,
    ) -> dict[str, Any]: ...


_logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of an async task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Metadata and result tracking for a submitted async task."""

    task_id: str
    module_id: str
    status: TaskStatus
    submitted_at: float
    started_at: float | None = None
    completed_at: float | None = None
    result: Any = None
    error: str | None = None


class AsyncTaskManager:
    """Manages background execution of modules via asyncio tasks.

    Limits concurrency with a semaphore and tracks task lifecycle.
    """

    def __init__(
        self,
        executor: ExecutorProtocol,
        max_concurrent: int = 10,
        max_tasks: int = 1000,
    ) -> None:
        self._executor = executor
        self._max_tasks = max_tasks
        self._tasks: dict[str, TaskInfo] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._async_tasks: dict[str, asyncio.Task[Any]] = {}

    async def submit(
        self,
        module_id: str,
        inputs: dict[str, Any],
        context: Context | None = None,
    ) -> str:
        """Submit a module for background execution.

        Creates a TaskInfo in PENDING state, spawns an asyncio.Task that
        acquires the concurrency semaphore before calling executor.call_async().

        Args:
            module_id: The module to execute.
            inputs: Input data for the module.
            context: Optional execution context.

        Returns:
            The generated task_id (UUID4 string).
        """
        if len(self._tasks) >= self._max_tasks:
            raise TaskLimitExceededError(max_tasks=self._max_tasks)

        task_id = str(uuid.uuid4())
        info = TaskInfo(
            task_id=task_id,
            module_id=module_id,
            status=TaskStatus.PENDING,
            submitted_at=time.time(),
        )
        self._tasks[task_id] = info

        async_task = asyncio.create_task(self._run(task_id, module_id, inputs, context))
        async_task.add_done_callback(lambda _: self._async_tasks.pop(task_id, None))
        self._async_tasks[task_id] = async_task

        return task_id

    def get_status(self, task_id: str) -> TaskInfo | None:
        """Return the TaskInfo for a task, or None if not found."""
        return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> Any:
        """Return the result of a completed task.

        Raises:
            KeyError: If the task_id is not found.
            RuntimeError: If the task is not in COMPLETED status.
        """
        info = self._tasks.get(task_id)
        if info is None:
            raise KeyError(f"Task not found: {task_id}")
        if info.status != TaskStatus.COMPLETED:
            raise RuntimeError(
                f"Task {task_id} is not completed (status={info.status.value})"
            )
        return info.result

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running or pending task.

        Uses the CancelToken on the context if available, otherwise falls back
        to asyncio.Task.cancel().

        Returns:
            True if the task was successfully cancelled, False otherwise.
        """
        info = self._tasks.get(task_id)
        if info is None:
            return False
        if info.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False

        async_task = self._async_tasks.get(task_id)
        if async_task is None:
            return False

        async_task.cancel()
        try:
            await async_task
        except asyncio.CancelledError:
            # Expected outcome of cooperative cancellation.
            pass
        except Exception as exc:
            # Unexpected failure from the task body (e.g., user code raised a
            # non-CancelledError exception during cleanup). Log at WARNING
            # with stack context — callers chose to cancel, so we must not
            # re-raise, but silently swallowing would hide real bugs.
            _logger.warning(
                "Task %s raised while being cancelled: %s",
                task_id,
                exc,
                exc_info=True,
            )

        # Status may have been updated by _run; force CANCELLED if still active
        if info.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            info.status = TaskStatus.CANCELLED
            info.completed_at = time.time()

        return True

    async def shutdown(self) -> None:
        """Cancel all pending/running tasks and wait for them to finish."""
        for task_id in list(self._async_tasks):
            await self.cancel(task_id)

    def list_tasks(self, status: TaskStatus | None = None) -> list[TaskInfo]:
        """Return all tasks, optionally filtered by status."""
        if status is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.status == status]

    def cleanup(self, max_age_seconds: float = 3600.0) -> int:
        """Remove terminal-state tasks older than max_age_seconds.

        Terminal states: COMPLETED, FAILED, CANCELLED.

        Returns:
            The number of tasks removed.
        """
        terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        now = time.time()
        to_remove: list[str] = []

        for task_id, info in self._tasks.items():
            if info.status not in terminal:
                continue
            ref_time = (
                info.completed_at
                if info.completed_at is not None
                else info.submitted_at
            )
            if now - ref_time >= max_age_seconds:
                to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]
            self._async_tasks.pop(task_id, None)

        return len(to_remove)

    async def _run(
        self,
        task_id: str,
        module_id: str,
        inputs: dict[str, Any],
        context: Context | None,
    ) -> None:
        """Internal coroutine that executes a module under the concurrency semaphore."""
        info = self._tasks[task_id]
        try:
            async with self._semaphore:
                info.status = TaskStatus.RUNNING
                info.started_at = time.time()

                result = await self._executor.call_async(module_id, inputs, context)

                info.status = TaskStatus.COMPLETED
                info.completed_at = time.time()
                info.result = result

        except asyncio.CancelledError:
            info.status = TaskStatus.CANCELLED
            info.completed_at = time.time()
            _logger.info("Task %s cancelled", task_id)

        except Exception as exc:
            info.status = TaskStatus.FAILED
            info.completed_at = time.time()
            info.error = str(exc)
            _logger.error("Task %s failed: %s", task_id, exc)
