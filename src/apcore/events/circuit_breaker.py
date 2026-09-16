"""Per-subscriber circuit breaker (Issue #36 – Event Management Hardening)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from apcore.events.emitter import ApCoreEvent, EventSubscriber

if TYPE_CHECKING:
    from apcore.events.emitter import EventEmitter

logger = logging.getLogger(__name__)

__all__ = ["CircuitState", "CircuitBreakerWrapper"]


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerWrapper:
    """Wraps an EventSubscriber with independent circuit-breaker logic.

    State machine:
        CLOSED → (consecutive_failures >= open_threshold) → OPEN
        OPEN → (recovery_window_ms elapsed) → HALF_OPEN
        HALF_OPEN → success → CLOSED
        HALF_OPEN → failure → OPEN
    """

    def __init__(
        self,
        subscriber: EventSubscriber,
        emitter: EventEmitter,
        timeout_ms: int = 5000,
        open_threshold: int = 5,
        recovery_window_ms: int = 60000,
    ) -> None:
        self._subscriber = subscriber
        self._emitter = emitter
        self._timeout_ms = timeout_ms
        self._open_threshold = open_threshold
        self._recovery_window_ms = recovery_window_ms

        self._state = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_at: datetime | None = None
        self._lock = threading.Lock()

    # EVT-001 — the wrapper stands in for the subscriber, so it must present
    # the subscriber's identity to the emitter.
    #
    # `EventEmitter._get_event_pattern` falls back to `"*"` for an object that
    # declares none, so wrapping a FILTERED subscriber in a circuit breaker
    # silently widened it to catch-all: an event type the operator deliberately
    # excluded was POSTed to the webhook. `subscriber_id` and `subscriber_type`
    # had the same shape — the DLQ payload and every emitter log line named the
    # wrapper's `repr()` (a heap address) instead of the subscriber the
    # operator configured. apcore-rust forwards all three (circuit_breaker.rs).
    #
    # Properties rather than copied attributes so a subscriber that rewrites
    # its own pattern after construction stays consistent with the wrapper.

    @property
    def event_pattern(self) -> str:
        pattern = getattr(self._subscriber, "event_pattern", None)
        return pattern if isinstance(pattern, str) else "*"

    @property
    def subscriber_id(self) -> Any:
        return getattr(self._subscriber, "subscriber_id", None)

    @property
    def subscriber_type(self) -> Any:
        stype = getattr(self._subscriber, "subscriber_type", None)
        if isinstance(stype, str):
            return stype
        return type(self._subscriber).__name__.lower().replace("subscriber", "").lstrip("_")

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    async def on_event(self, event: ApCoreEvent) -> None:
        import asyncio

        try:
            self._check_recovery()
        except Exception:
            logger.exception("CircuitBreakerWrapper._check_recovery raised unexpectedly")
            return

        with self._lock:
            current_state = self._state

        if current_state == CircuitState.OPEN:
            return

        circuit_event: ApCoreEvent | None = None
        try:
            await asyncio.wait_for(
                self._subscriber.on_event(event),
                timeout=self._timeout_ms / 1000.0,
            )
            circuit_event = self._on_success()
        except Exception as exc:
            circuit_event = self._on_failure(exc)

        if circuit_event is not None:
            try:
                self._emitter.emit(circuit_event)
            except Exception:
                logger.exception(
                    "CircuitBreakerWrapper failed to emit circuit event %s",
                    circuit_event.event_type,
                )

    def _check_recovery(self) -> None:
        """Transition OPEN → HALF_OPEN if recovery window has elapsed."""
        with self._lock:
            if self._state != CircuitState.OPEN or self._last_failure_at is None:
                return
            elapsed_ms = (datetime.now(timezone.utc) - self._last_failure_at).total_seconds() * 1000
            if elapsed_ms >= self._recovery_window_ms:
                self._state = CircuitState.HALF_OPEN

    def _on_success(self) -> ApCoreEvent | None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0
                return self._make_event(
                    "apcore.subscriber.circuit_closed",
                    "info",
                    {
                        "subscriber_type": type(self._subscriber).__name__,
                        "recovery_attempt": True,
                    },
                )
            self._consecutive_failures = 0
            return None

    def _on_failure(self, error: Exception) -> ApCoreEvent | None:
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_at = datetime.now(timezone.utc)

            opens = self._state == CircuitState.HALF_OPEN or (
                self._state == CircuitState.CLOSED and self._consecutive_failures >= self._open_threshold
            )
            if opens:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit opened for subscriber %s after %d consecutive failures: %s",
                    type(self._subscriber).__name__,
                    self._consecutive_failures,
                    error,
                )
                return self._make_event(
                    "apcore.subscriber.circuit_opened",
                    "warn",
                    {
                        "subscriber_type": type(self._subscriber).__name__,
                        "consecutive_failures": self._consecutive_failures,
                    },
                )
            return None

    def _make_event(self, event_type: str, severity: str, data: dict[str, Any]) -> ApCoreEvent:
        return ApCoreEvent(
            event_type=event_type,
            module_id=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            severity=severity,
            data=data,
        )
