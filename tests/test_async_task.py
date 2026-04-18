"""Tests for AsyncTaskManager, TaskStatus, and TaskInfo."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from apcore.async_task import AsyncTaskManager, TaskInfo, TaskStatus
from apcore.context import Context
from apcore.executor import Executor
from apcore.registry import Registry


# === Helper modules ===


class SimpleModule:
    """Module that returns immediately."""

    input_schema = None
    output_schema = None

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        return {"value": inputs.get("x", 0)}


class AsyncSimpleModule:
    """Async module that returns immediately."""

    input_schema = None
    output_schema = None

    async def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        return {"value": inputs.get("x", 0)}


class FailingModule:
    """Module that always raises."""

    input_schema = None
    output_schema = None

    def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        raise RuntimeError("intentional failure")


class SlowAsyncModule:
    """Async module that sleeps for a configurable duration."""

    input_schema = None
    output_schema = None

    async def execute(self, inputs: dict[str, Any], context: Context) -> dict[str, Any]:
        delay = inputs.get("delay", 1.0)
        await asyncio.sleep(delay)
        return {"done": True}


# === Fixtures ===


@pytest.fixture
def registry() -> Registry:
    reg = Registry()
    reg.register("test.simple", SimpleModule())
    reg.register("test.async_simple", AsyncSimpleModule())
    reg.register("test.failing", FailingModule())
    reg.register("test.slow", SlowAsyncModule())
    return reg


@pytest.fixture
def executor(registry: Registry) -> Executor:
    return Executor(registry=registry)


@pytest.fixture
def manager(executor: Executor) -> AsyncTaskManager:
    return AsyncTaskManager(executor, max_concurrent=10)


# === Tests ===


class TestTaskStatusTransitions:
    """Submit task and verify PENDING -> RUNNING -> COMPLETED."""

    @pytest.mark.asyncio
    async def test_submit_completes_successfully(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.simple", {"x": 42})

        # Task should exist immediately after submit
        info = manager.get_status(task_id)
        assert info is not None
        assert info.module_id == "test.simple"

        # Allow the background task to complete
        await asyncio.sleep(0.1)

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.COMPLETED
        assert info.result == {"value": 42}
        assert info.started_at is not None
        assert info.completed_at is not None
        assert info.error is None

    @pytest.mark.asyncio
    async def test_submit_async_module(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.async_simple", {"x": 7})
        await asyncio.sleep(0.1)

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.COMPLETED
        assert info.result == {"value": 7}


class TestTaskFailure:
    """Submit task that fails -> status FAILED with error message."""

    @pytest.mark.asyncio
    async def test_failed_task_has_error(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.failing", {})
        await asyncio.sleep(0.1)

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.FAILED
        assert info.error is not None
        assert "intentional failure" in info.error
        assert info.completed_at is not None
        assert info.result is None


class TestTaskCancellation:
    """Cancel running task -> status CANCELLED."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.slow", {"delay": 10.0})
        # Give it time to start
        await asyncio.sleep(0.1)

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.RUNNING

        result = await manager.cancel(task_id)
        assert result is True

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.CANCELLED
        assert info.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, manager: AsyncTaskManager) -> None:
        result = await manager.cancel("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_completed_task(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.simple", {"x": 1})
        await asyncio.sleep(0.1)

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.COMPLETED

        result = await manager.cancel(task_id)
        assert result is False


class TestConcurrencyLimit:
    """Verify max_concurrent is respected."""

    @pytest.mark.asyncio
    async def test_max_concurrent_respected(self, executor: Executor) -> None:
        max_concurrent = 2
        mgr = AsyncTaskManager(executor, max_concurrent=max_concurrent)

        # Submit 4 slow tasks
        task_ids = []
        for _ in range(4):
            tid = await mgr.submit("test.slow", {"delay": 5.0})
            task_ids.append(tid)

        # Allow tasks to start competing for the semaphore
        await asyncio.sleep(0.2)

        tasks = mgr.list_tasks()
        running = [t for t in tasks if t.status == TaskStatus.RUNNING]
        pending = [t for t in tasks if t.status == TaskStatus.PENDING]

        assert len(running) <= max_concurrent
        # Some should still be pending since we only allow 2 concurrent
        assert len(pending) + len(running) == 4

        # Cleanup: cancel all
        for tid in task_ids:
            await mgr.cancel(tid)


class TestGetResult:
    """get_result() raises for non-completed tasks."""

    @pytest.mark.asyncio
    async def test_get_result_returns_value(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.simple", {"x": 99})
        await asyncio.sleep(0.1)

        result = manager.get_result(task_id)
        assert result == {"value": 99}

    def test_get_result_raises_for_unknown_task(self, manager: AsyncTaskManager) -> None:
        with pytest.raises(KeyError, match="Task not found"):
            manager.get_result("no-such-task")

    @pytest.mark.asyncio
    async def test_get_result_raises_for_pending_task(self, manager: AsyncTaskManager) -> None:
        # Submit a slow task so it stays in PENDING/RUNNING
        task_id = await manager.submit("test.slow", {"delay": 10.0})

        with pytest.raises(RuntimeError, match="not completed"):
            manager.get_result(task_id)

        await manager.cancel(task_id)


class TestListTasks:
    """list_tasks() returns all or filtered tasks."""

    @pytest.mark.asyncio
    async def test_list_all_tasks(self, manager: AsyncTaskManager) -> None:
        await manager.submit("test.simple", {"x": 1})
        await manager.submit("test.simple", {"x": 2})
        await asyncio.sleep(0.1)

        all_tasks = manager.list_tasks()
        assert len(all_tasks) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_filtered(self, manager: AsyncTaskManager) -> None:
        await manager.submit("test.simple", {"x": 1})
        await manager.submit("test.failing", {})
        await asyncio.sleep(0.1)

        completed = manager.list_tasks(status=TaskStatus.COMPLETED)
        failed = manager.list_tasks(status=TaskStatus.FAILED)
        assert len(completed) == 1
        assert len(failed) == 1


class TestCleanup:
    """cleanup() removes old completed tasks."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_tasks(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.simple", {"x": 1})
        await asyncio.sleep(0.1)

        info = manager.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.COMPLETED

        # With max_age=0, everything completed should be cleaned
        removed = manager.cleanup(max_age_seconds=0.0)
        assert removed == 1
        assert manager.get_status(task_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_tasks(self, manager: AsyncTaskManager) -> None:
        await manager.submit("test.simple", {"x": 1})
        await asyncio.sleep(0.1)

        # With a large max_age, nothing should be removed
        removed = manager.cleanup(max_age_seconds=3600.0)
        assert removed == 0
        assert len(manager.list_tasks()) == 1

    @pytest.mark.asyncio
    async def test_cleanup_preserves_running_tasks(self, manager: AsyncTaskManager) -> None:
        task_id = await manager.submit("test.slow", {"delay": 10.0})
        await asyncio.sleep(0.1)

        # Running tasks should not be cleaned up even with max_age=0
        removed = manager.cleanup(max_age_seconds=0.0)
        assert removed == 0

        await manager.cancel(task_id)


class TestGetStatusEdgeCases:
    """get_status() edge cases."""

    def test_get_status_unknown_id(self, manager: AsyncTaskManager) -> None:
        assert manager.get_status("nonexistent") is None


class TestTaskInfo:
    """TaskInfo dataclass basics."""

    def test_task_info_creation(self) -> None:
        info = TaskInfo(
            task_id="abc",
            module_id="test.mod",
            status=TaskStatus.PENDING,
            submitted_at=time.time(),
        )
        assert info.task_id == "abc"
        assert info.module_id == "test.mod"
        assert info.status == TaskStatus.PENDING
        assert info.started_at is None
        assert info.completed_at is None
        assert info.result is None
        assert info.error is None


class TestTaskStatusEnum:
    """TaskStatus enum values."""

    def test_status_values(self) -> None:
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_status_is_str(self) -> None:
        assert isinstance(TaskStatus.PENDING, str)


class TestMaxTasksLimit:
    """submit() raises TaskLimitExceededError when task limit is reached."""

    @pytest.mark.asyncio
    async def test_submit_exceeds_max_tasks(self, executor: Executor) -> None:
        from apcore.errors import TaskLimitExceededError

        max_tasks = 3
        mgr = AsyncTaskManager(executor, max_concurrent=10, max_tasks=max_tasks)

        for _ in range(max_tasks):
            await mgr.submit("test.simple", {"x": 1})

        with pytest.raises(TaskLimitExceededError) as exc_info:
            await mgr.submit("test.simple", {"x": 1})
        assert exc_info.value.code == "TASK_LIMIT_EXCEEDED"
        assert exc_info.value.details["max_tasks"] == max_tasks

    @pytest.mark.asyncio
    async def test_submit_at_limit_after_cleanup(self, executor: Executor) -> None:
        max_tasks = 2
        mgr = AsyncTaskManager(executor, max_concurrent=10, max_tasks=max_tasks)

        await mgr.submit("test.simple", {"x": 1})
        await mgr.submit("test.simple", {"x": 2})
        await asyncio.sleep(0.1)

        # Clean up completed tasks to free slots
        mgr.cleanup(max_age_seconds=0.0)

        # Now we should be able to submit again
        task_id = await mgr.submit("test.simple", {"x": 3})
        assert task_id is not None

    @pytest.mark.asyncio
    async def test_max_tasks_counts_only_active_tasks(self, executor: Executor) -> None:
        """max_tasks is a concurrency cap, not a lifetime cap.

        Once tasks reach a terminal state, they must not count against the
        limit even without an explicit cleanup().
        """
        max_tasks = 2
        mgr = AsyncTaskManager(executor, max_concurrent=10, max_tasks=max_tasks)

        # Fill the limit with tasks and let them complete.
        for _ in range(max_tasks):
            await mgr.submit("test.simple", {"x": 1})
        await asyncio.sleep(0.1)

        # Terminal tasks stay in _tasks for get_status()/get_result(), but
        # they must not block new submissions.
        assert all(
            info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            for info in mgr._tasks.values()
        )

        # Submitting again should succeed without calling cleanup().
        new_id = await mgr.submit("test.simple", {"x": 99})
        assert new_id in mgr._tasks


class TestShutdown:
    """shutdown() cancels all pending/running tasks."""

    @pytest.fixture
    def executor(self) -> Executor:
        reg = Registry()
        reg.register("slow_module", SlowAsyncModule())
        return Executor(registry=reg)

    @pytest.mark.asyncio
    async def test_shutdown_cancels_all_tasks(self) -> None:
        reg = Registry()
        reg.register("slow_module", SlowAsyncModule())
        executor = Executor(registry=reg)
        mgr = AsyncTaskManager(executor=executor, max_concurrent=2)
        for _ in range(3):
            await mgr.submit("slow_module", {})
        await mgr.shutdown()
        for t in mgr.list_tasks():
            assert t.status in (TaskStatus.CANCELLED, TaskStatus.COMPLETED)


class TestAsyncTaskAutoCleanup:
    """Completed asyncio.Task objects are removed from _async_tasks automatically."""

    @pytest.mark.asyncio
    async def test_done_callback_removes_async_task(self, executor: Executor) -> None:
        mgr = AsyncTaskManager(executor, max_concurrent=10)
        task_id = await mgr.submit("test.simple", {"x": 1})

        # Allow the background task to complete and callback to fire
        await asyncio.sleep(0.1)

        # The asyncio.Task should have been auto-removed from _async_tasks
        assert task_id not in mgr._async_tasks

        # But the TaskInfo should still be in _tasks
        info = mgr.get_status(task_id)
        assert info is not None
        assert info.status == TaskStatus.COMPLETED
