"""Event subscribers for webhook and A2A protocol delivery (PRD F9)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

import aiohttp

from apcore.events.emitter import ApCoreEvent

__all__ = ["WebhookSubscriber", "A2ASubscriber"]

logger = logging.getLogger(__name__)


class WebhookSubscriber:
    """Delivers events via HTTP POST to a webhook URL.

    Retries on 5xx and connection errors up to ``retry_count`` times.
    Does not retry on 4xx responses. Enforces ``timeout_ms``.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        retry_count: int = 3,
        timeout_ms: int = 5000,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._retry_count = retry_count
        self._timeout_ms = timeout_ms

    async def on_event(self, event: ApCoreEvent) -> None:
        """Send the event as a JSON POST request to the configured URL."""
        payload = asdict(event)
        timeout = aiohttp.ClientTimeout(total=self._timeout_ms / 1000.0)
        merged_headers = {"Content-Type": "application/json", **self._headers}

        attempts = 1 + self._retry_count  # initial + retries
        last_error: Exception | None = None

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(attempts):
                try:
                    async with session.post(self._url, json=payload, headers=merged_headers) as response:
                        if response.status < 500:
                            # Success or 4xx -- no retry
                            if response.status >= 400:
                                logger.warning(
                                    "Webhook %s returned %d for event %s",
                                    self._url,
                                    response.status,
                                    event.event_type,
                                )
                            return
                        # 5xx -- retry
                        last_error = RuntimeError(f"Webhook returned {response.status}")
                        logger.warning(
                            "Webhook %s returned %d (attempt %d/%d)",
                            self._url,
                            response.status,
                            attempt + 1,
                            attempts,
                        )
                except (OSError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    logger.warning(
                        "Webhook %s failed (attempt %d/%d): %s",
                        self._url,
                        attempt + 1,
                        attempts,
                        exc,
                    )

        if last_error is not None:
            logger.error(
                "Webhook %s delivery failed after %d attempts: %s",
                self._url,
                attempts,
                last_error,
            )


class A2ASubscriber:
    """Delivers events via the A2A protocol to the platform.

    Sends a POST with ``skillId="apevo.event_receiver"`` and the
    serialized event in the payload. Failures are logged, not raised.
    """

    def __init__(
        self,
        platform_url: str,
        auth: str | dict[str, str] | None = None,
        timeout_ms: int = 5000,
    ) -> None:
        self._platform_url = platform_url
        self._auth = auth
        self._timeout_ms = timeout_ms

    async def on_event(self, event: ApCoreEvent) -> None:
        """Send the event to the A2A platform endpoint."""
        payload = {
            "skillId": "apevo.event_receiver",
            "event": asdict(event),
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if isinstance(self._auth, str):
            headers["Authorization"] = f"Bearer {self._auth}"
        elif isinstance(self._auth, dict):
            headers.update(self._auth)

        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout_ms / 1000.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._platform_url, json=payload, headers=headers) as response:
                    if response.status >= 400:
                        logger.error(
                            "A2A delivery to %s failed with status %d",
                            self._platform_url,
                            response.status,
                        )
        except Exception:
            logger.exception(
                "A2A delivery to %s failed for event %s",
                self._platform_url,
                event.event_type,
            )
