# Task: WebhookSubscriber and A2ASubscriber (PRD F9)

## Goal

Implement `WebhookSubscriber` and `A2ASubscriber` classes that conform to the `EventSubscriber` protocol, enabling event delivery via HTTP webhooks and A2A protocol respectively.

## Files Involved

- `src/apcore/events/subscribers.py` -- `WebhookSubscriber` and `A2ASubscriber` classes
- `tests/events/test_subscribers.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/events/test_subscribers.py` with tests for:

**WebhookSubscriber:**

- **test_webhook_subscriber_sends_post_request**: Create subscriber with URL; call `on_event()`; verify HTTP POST sent to URL with JSON-serialized event body
- **test_webhook_subscriber_includes_custom_headers**: Create subscriber with `headers={"X-Api-Key": "secret"}`; verify headers included in request
- **test_webhook_subscriber_retries_on_5xx**: Mock server returning 500 twice then 200; verify request is retried and succeeds
- **test_webhook_subscriber_retries_on_connection_error**: Mock connection error twice then success; verify retries work
- **test_webhook_subscriber_respects_retry_count**: Set `retry_count=2`; mock 3 consecutive 500s; verify only 2 retries (3 total attempts)
- **test_webhook_subscriber_enforces_timeout**: Set `timeout_ms=100`; mock slow server (2s response); verify timeout error raised/logged
- **test_webhook_subscriber_does_not_retry_on_4xx**: Mock 400 response; verify no retry
- **test_webhook_subscriber_serializes_event_to_json**: Verify the POST body contains `event_type`, `module_id`, `timestamp`, `severity`, `data`

**A2ASubscriber:**

- **test_a2a_subscriber_sends_via_client**: Create subscriber with `platform_url` and `auth`; call `on_event()`; verify A2A client sends message with `skillId="apevo.event_receiver"`
- **test_a2a_subscriber_includes_event_in_payload**: Verify the sent message payload contains the serialized event
- **test_a2a_subscriber_handles_send_failure**: Mock A2A client raising exception; verify error is logged but not raised

**Both:**

- **test_subscriber_conforms_to_protocol**: Verify both classes satisfy `EventSubscriber` protocol (have `async on_event()`)
- **test_subscriber_instantiation_failure_logged**: Mock a constructor dependency failing; verify error is logged, not raised

### 2. Implement WebhookSubscriber

Create `src/apcore/events/subscribers.py`:

```python
class WebhookSubscriber:
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
        # JSON-serialize event
        # HTTP POST with retries on 5xx/connection error
        # Enforce timeout
        # Log failures
```

- Use `urllib.request` or `httpx`/`aiohttp` (prefer stdlib to minimize deps)
- Retry logic: up to `retry_count` retries on 5xx or connection errors
- No retry on 4xx
- Timeout enforcement via `timeout_ms`

### 3. Implement A2ASubscriber

```python
class A2ASubscriber:
    def __init__(
        self,
        platform_url: str,
        auth: str | dict[str, str] | None = None,
    ) -> None:
        self._platform_url = platform_url
        self._auth = auth

    async def on_event(self, event: ApCoreEvent) -> None:
        # Send via A2A protocol with skillId="apevo.event_receiver"
        # Log failures, do not raise
```

### 4. Verify tests pass

Run `pytest tests/events/test_subscribers.py -v`.

## Acceptance Criteria

- [ ] `WebhookSubscriber` sends HTTP POST with JSON-serialized event
- [ ] `WebhookSubscriber` includes custom headers in requests
- [ ] `WebhookSubscriber` retries on 5xx and connection errors, up to `retry_count`
- [ ] `WebhookSubscriber` does not retry on 4xx
- [ ] `WebhookSubscriber` enforces `timeout_ms`
- [ ] `A2ASubscriber` sends events via A2A protocol with `skillId="apevo.event_receiver"`
- [ ] Both classes conform to `EventSubscriber` protocol
- [ ] Instantiation failures are logged, not raised
- [ ] Send failures are logged, not raised
- [ ] Full type annotations
- [ ] Tests achieve >= 90% coverage using mocks for HTTP/A2A

## Dependencies

- `apcore.events.emitter.ApCoreEvent`, `EventSubscriber` (Task 4)

## Estimated Time

4 hours
