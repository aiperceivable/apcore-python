"""Global event bus with fan-out delivery and subscriber error isolation."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApCoreEvent:
    """Immutable event emitted by the apcore event bus."""

    event_type: str
    module_id: str | None
    timestamp: str
    severity: str
    data: dict[str, Any]


@runtime_checkable
class EventSubscriber(Protocol):
    """Protocol for objects that can receive apcore events."""

    async def on_event(self, event: ApCoreEvent) -> None: ...


class EventEmitter:
    """Thread-safe global event bus with non-blocking fan-out delivery.

    Uses a bounded ThreadPoolExecutor with a persistent asyncio event loop
    for efficient async subscriber delivery. Errors in one subscriber do
    not affect others.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._subscribers: list[EventSubscriber] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="apcore-event",
        )
        self._pending_futures: list[Future[None]] = []
        self._pending_lock = threading.Lock()
        # Persistent event loop for async subscriber delivery
        self._loop = asyncio.new_event_loop()
        self._loop_lock = threading.Lock()

    def subscribe(self, subscriber: EventSubscriber) -> None:
        """Add a subscriber to receive future events.

        Raises:
            TypeError: If ``subscriber.on_event`` is not a coroutine function.
                The emitter awaits deliveries via ``run_until_complete``; a
                plain function would fail at delivery time with a confusing
                error. Failing in ``subscribe`` gives callers an actionable
                signal at registration time.
        """
        if not asyncio.iscoroutinefunction(getattr(subscriber, "on_event", None)):
            raise TypeError(
                f"Subscriber {subscriber!r} must define an async on_event(event) "
                "method; synchronous on_event is not supported."
            )
        with self._lock:
            self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: EventSubscriber) -> None:
        """Remove a subscriber. No-op if not found."""
        with self._lock:
            try:
                self._subscribers.remove(subscriber)
            except ValueError:
                pass

    def emit(self, event: ApCoreEvent) -> None:
        """Fan-out event to all subscribers via thread pool.

        Returns immediately. Subscriber errors are logged but not propagated.
        """
        with self._lock:
            snapshot = list(self._subscribers)

        if not snapshot:
            return

        future = self._executor.submit(self._deliver, snapshot, event)
        with self._pending_lock:
            # Clean up completed futures
            self._pending_futures = [f for f in self._pending_futures if not f.done()]
            self._pending_futures.append(future)

    def flush(self, timeout: float = 5.0) -> None:
        """Wait for all pending event deliveries to complete.

        Args:
            timeout: Maximum seconds to wait for all pending deliveries.
        """
        with self._pending_lock:
            futures = list(self._pending_futures)
        for future in futures:
            try:
                future.result(timeout=timeout)
            except Exception:
                pass  # Errors already logged in _deliver
        with self._pending_lock:
            self._pending_futures = [f for f in self._pending_futures if not f.done()]

    def _deliver(self, subscribers: list[EventSubscriber], event: ApCoreEvent) -> None:
        """Deliver event to each subscriber using the persistent event loop."""
        with self._loop_lock:
            for subscriber in subscribers:
                try:
                    self._loop.run_until_complete(subscriber.on_event(event))
                except Exception:
                    logger.exception(
                        "Subscriber %r failed handling event %s",
                        subscriber,
                        event.event_type,
                    )
