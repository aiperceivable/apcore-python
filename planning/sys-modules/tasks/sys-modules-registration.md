# Task: Auto-Registration of sys.* Modules and Middleware (PRD Integration)

## Goal

Implement the `register_sys_modules()` function that wires together all sys.* modules and middleware based on configuration, and integrate it into the `APCore` client initialization.

## Files Involved

- `src/apcore/sys_modules/registration.py` -- `register_sys_modules()` function
- `src/apcore/client.py` -- Modify `APCore.__init__()` to call `register_sys_modules()`
- `tests/sys_modules/test_registration.py` -- Unit tests

## Steps

### 1. Write failing tests (TDD)

Create `tests/sys_modules/test_registration.py` with tests for:

- **test_register_sys_modules_disabled_noop**: Config with `sys_modules.enabled=False`; call `register_sys_modules()`; verify no modules registered, no middleware added
- **test_register_sys_modules_creates_error_history**: Config with `sys_modules.enabled=True`; call; verify `ErrorHistory` created with config values for `max_entries_per_module` and `max_total_entries`
- **test_register_sys_modules_registers_error_history_middleware**: Verify `ErrorHistoryMiddleware` is added to executor
- **test_register_sys_modules_registers_health_summary**: Verify `system.health.summary` is registered in registry
- **test_register_sys_modules_registers_health_module**: Verify `system.health.module` is registered in registry
- **test_register_sys_modules_registers_manifest_module**: Verify `system.manifest.module` is registered in registry
- **test_register_sys_modules_events_disabled_no_emitter**: Config with `sys_modules.events.enabled=False`; verify no `EventEmitter` created, no `PlatformNotifyMiddleware` added
- **test_register_sys_modules_events_enabled_creates_emitter**: Config with `sys_modules.events.enabled=True`; verify `EventEmitter` created
- **test_register_sys_modules_events_registers_platform_notify_middleware**: Events enabled; verify `PlatformNotifyMiddleware` added to executor with correct thresholds
- **test_register_sys_modules_events_instantiates_subscribers**: Config with webhook subscriber in `sys_modules.events.subscribers`; verify subscriber created and subscribed to emitter
- **test_register_sys_modules_subscriber_failure_logged**: Config with invalid subscriber config; verify error is logged but registration continues
- **test_register_sys_modules_bridges_registry_events**: Events enabled; verify registry `on("register")` and `on("unregister")` callbacks bridge to EventEmitter
- **test_register_sys_modules_returns_context**: Verify function returns a dict/object with references to created components (ErrorHistory, EventEmitter, etc.) for testing/inspection
- **test_apcore_client_calls_register_sys_modules**: Create `APCore` with config having `sys_modules.enabled=True`; verify sys modules are registered

### 2. Implement register_sys_modules()

Create `src/apcore/sys_modules/registration.py`:

```python
def register_sys_modules(
    registry: Registry,
    executor: Executor,
    config: Config,
    metrics_collector: MetricsCollector | None = None,
) -> dict[str, Any]:
    """Auto-register all sys.* modules and middleware based on config.

    Args:
        registry: Module registry.
        executor: Executor for middleware registration.
        config: Configuration with sys_modules section.
        metrics_collector: Optional MetricsCollector instance.

    Returns:
        Dict with references to created components for testing/inspection.
    """
    result: dict[str, Any] = {}

    if not config.get("sys_modules.enabled", False):
        return result

    # 1. Create ErrorHistory
    max_per_module = config.get(
        "sys_modules.error_history.max_entries_per_module", 50
    )
    max_total = config.get(
        "sys_modules.error_history.max_total_entries", 1000
    )
    error_history = ErrorHistory(
        max_entries_per_module=max_per_module,
        max_total_entries=max_total,
    )
    result["error_history"] = error_history

    # 2. Register ErrorHistoryMiddleware
    eh_middleware = ErrorHistoryMiddleware(error_history)
    executor.use(eh_middleware)
    result["error_history_middleware"] = eh_middleware

    # 3. Register health/manifest sys.* modules
    health_summary = HealthSummaryModule(
        registry=registry,
        metrics_collector=metrics_collector,
        error_history=error_history,
        config=config,
    )
    registry.register("system.health.summary", health_summary)

    health_module = HealthModuleModule(
        registry=registry,
        metrics_collector=metrics_collector,
        error_history=error_history,
    )
    registry.register("system.health.module", health_module)

    manifest_module = ManifestModuleModule(
        registry=registry,
        config=config,
    )
    registry.register("system.manifest.module", manifest_module)

    # 4. Events subsystem (if enabled)
    if config.get("sys_modules.events.enabled", False):
        event_emitter = EventEmitter()
        result["event_emitter"] = event_emitter

        # PlatformNotifyMiddleware
        error_rate_threshold = config.get(
            "sys_modules.events.thresholds.error_rate", 0.1
        )
        latency_p99_threshold = config.get(
            "sys_modules.events.thresholds.latency_p99_ms", 5000.0
        )
        pn_middleware = PlatformNotifyMiddleware(
            event_emitter=event_emitter,
            metrics_collector=metrics_collector,
            error_rate_threshold=error_rate_threshold,
            latency_p99_threshold_ms=latency_p99_threshold,
        )
        executor.use(pn_middleware)
        result["platform_notify_middleware"] = pn_middleware

        # Instantiate subscribers
        subscribers_config = config.get(
            "sys_modules.events.subscribers", []
        )
        for sub_cfg in subscribers_config:
            try:
                subscriber = _create_subscriber(sub_cfg)
                event_emitter.subscribe(subscriber)
            except Exception:
                logger.warning(
                    "Failed to instantiate subscriber: %s",
                    sub_cfg,
                    exc_info=True,
                )

        # Bridge registry events to EventEmitter
        _bridge_registry_events(registry, event_emitter)

    return result
```

### 3. Implement helper functions

- `_create_subscriber(config: dict) -> EventSubscriber`: Factory for `WebhookSubscriber` / `A2ASubscriber` from config dict
- `_bridge_registry_events(registry: Registry, emitter: EventEmitter) -> None`: Register `on("register")` and `on("unregister")` callbacks that emit `module_registered` / `module_unregistered` events

### 4. Modify APCore client

In `src/apcore/client.py`, update `APCore.__init__()`:

```python
def __init__(self, ...) -> None:
    ...
    # After registry and executor are created:
    if self.config is not None:
        from apcore.sys_modules.registration import register_sys_modules
        self._sys_modules_context = register_sys_modules(
            registry=self.registry,
            executor=self.executor,
            config=self.config,
        )
```

### 5. Verify tests pass

Run `pytest tests/sys_modules/test_registration.py -v`.

## Acceptance Criteria

- [ ] `register_sys_modules()` returns immediately when `sys_modules.enabled=False`
- [ ] `ErrorHistory` created with config values for limits
- [ ] `ErrorHistoryMiddleware` added to executor
- [ ] `system.health.summary`, `system.health.module`, `system.manifest.module` registered in registry
- [ ] When `sys_modules.events.enabled=True`: `EventEmitter` created, `PlatformNotifyMiddleware` added
- [ ] Subscribers instantiated from config; failures logged, not raised
- [ ] Registry events bridged to EventEmitter when events enabled
- [ ] `APCore` client calls `register_sys_modules()` during initialization
- [ ] Function returns context dict with references to created components
- [ ] Full type annotations
- [ ] Tests achieve >= 90% coverage

## Dependencies

- All previous tasks (1-9)
- `apcore.registry.Registry`
- `apcore.executor.Executor`
- `apcore.config.Config`
- `apcore.observability.metrics.MetricsCollector`

## Estimated Time

4 hours
