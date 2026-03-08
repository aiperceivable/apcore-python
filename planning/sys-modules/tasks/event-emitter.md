# Task: EventEmitter Global Event Bus (PRD F7)

## Goal

Implement a global event bus (`EventEmitter`) with `ApCoreEvent` frozen dataclass, `EventSubscriber` protocol, and fan-out emit semantics. Subscriber errors are isolated. Emit is non-blocking.

## Files Involved

- `src/apcore/events/__init__.py` -- Package init
- `src/apcore/events/emitter.py` -- `ApCoreEvent`, `EventSubscriber`, `EventEmitter`
- `tests/events/__init__.py` -- Package init
- `tests/events/test_emitter.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/events/test_emitter.py` with tests for:

- **test_apcore_event_is_frozen**: Verify `ApCoreEvent` is a frozen dataclass; attempting to set an attribute raises `FrozenInstanceError`
- **test_apcore_event_fields**: Verify fields: `event_type` (str), `module_id` (str | None), `timestamp` (str), `severity` (str), `data` (dict)
- **test_subscribe_and_emit**: Subscribe one subscriber; emit an event; verify subscriber received it
- **test_emit_fans_out_to_all_subscribers**: Subscribe 3 subscribers; emit one event; verify all 3 received it
- **test_unsubscribe_stops_delivery**: Subscribe, then unsubscribe; emit event; verify subscriber did NOT receive it
- **test_subscriber_error_does_not_block_others**: Subscribe 3 subscribers where the second raises an exception; emit; verify first and third still received the event
- **test_emit_is_non_blocking**: Emit an event with a slow subscriber (sleeps 1s); verify emit() returns immediately (< 100ms)
- **test_emit_with_no_subscribers**: Emit event with no subscribers; verify no error
- **test_event_subscriber_protocol**: Verify `EventSubscriber` is a `Protocol` with `async on_event(event: ApCoreEvent) -> None`
- **test_emit_delivers_correct_event_data**: Emit event with specific `data`; verify subscriber receives exact same data

### 2. Implement ApCoreEvent dataclass

Create `src/apcore/events/emitter.py`:

```python
@dataclass(frozen=True)
class ApCoreEvent:
    event_type: str
    module_id: str | None
    timestamp: str
    severity: str
    data: dict[str, Any]
```

### 3. Implement EventSubscriber Protocol

```python
@runtime_checkable
class EventSubscriber(Protocol):
    async def on_event(self, event: ApCoreEvent) -> None: ...
```

### 4. Implement EventEmitter

- `__init__()`: Initialize `_subscribers: list[EventSubscriber]` and `_lock: threading.Lock`
- `subscribe(subscriber: EventSubscriber) -> None`: Add subscriber under lock
- `unsubscribe(subscriber: EventSubscriber) -> None`: Remove subscriber under lock
- `emit(event: ApCoreEvent) -> None`:
  - Take snapshot of subscribers under lock
  - Fan-out via `asyncio.create_task` or `threading.Thread` (non-blocking)
  - Each subscriber call wrapped in try/except; log errors but do not propagate
- Emit must return immediately (non-blocking)

### 5. Create package __init__.py files

- `src/apcore/events/__init__.py`: Export `ApCoreEvent`, `EventSubscriber`, `EventEmitter`
- `tests/events/__init__.py`: Empty file

### 6. Verify tests pass

Run `pytest tests/events/test_emitter.py -v`.

## Acceptance Criteria

- [ ] `ApCoreEvent` is a frozen dataclass with `event_type`, `module_id`, `timestamp`, `severity`, `data`
- [ ] `EventSubscriber` is a `Protocol` with `async on_event(event)` method
- [ ] `EventEmitter.subscribe()` and `unsubscribe()` manage subscriber list under lock
- [ ] `EventEmitter.emit()` fans out to all subscribers
- [ ] Subscriber errors are isolated (logged, not propagated)
- [ ] `emit()` is non-blocking (returns immediately)
- [ ] Full type annotations on all classes and methods
- [ ] Tests achieve >= 90% coverage of `emitter.py`
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

None -- EventEmitter is independent.

## Estimated Time

3 hours
