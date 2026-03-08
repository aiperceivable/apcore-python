"""Auto-registration of sys.* modules and middleware from config (PRD F1-F9)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from apcore.config import Config
from apcore.events.emitter import ApCoreEvent, EventEmitter, EventSubscriber
from apcore.events.subscribers import A2ASubscriber, WebhookSubscriber
from apcore.executor import Executor
from apcore.middleware.error_history import ErrorHistoryMiddleware
from apcore.middleware.platform_notify import PlatformNotifyMiddleware
from apcore.observability.error_history import ErrorHistory
from apcore.observability.metrics import MetricsCollector
from apcore.registry.registry import Registry
from apcore.sys_modules.control import ReloadModuleModule, ToggleFeatureModule, UpdateConfigModule
from apcore.sys_modules.health import HealthModuleModule, HealthSummaryModule
from apcore.sys_modules.manifest import ManifestFullModule, ManifestModuleModule
from apcore.sys_modules.usage import UsageModuleModule, UsageSummaryModule
from apcore.observability.usage import UsageCollector, UsageMiddleware

logger = logging.getLogger(__name__)

__all__ = [
    "register_sys_modules",
    "register_subscriber_type",
    "unregister_subscriber_type",
    "reset_subscriber_registry",
]


# ---------------------------------------------------------------------------
# Subscriber type registry — extensible factory for EventSubscriber types
# ---------------------------------------------------------------------------

#: Maps subscriber type name → factory function(config_dict) → EventSubscriber
_subscriber_factories: dict[str, Callable[[dict[str, Any]], EventSubscriber]] = {}


def _default_webhook_factory(cfg: dict[str, Any]) -> EventSubscriber:
    return WebhookSubscriber(
        url=cfg["url"],
        headers=cfg.get("headers"),
        retry_count=cfg.get("retry_count", 3),
        timeout_ms=cfg.get("timeout_ms", 5000),
    )


def _default_a2a_factory(cfg: dict[str, Any]) -> EventSubscriber:
    return A2ASubscriber(
        platform_url=cfg["platform_url"],
        auth=cfg.get("auth"),
    )


# Register built-in types
_subscriber_factories["webhook"] = _default_webhook_factory
_subscriber_factories["a2a"] = _default_a2a_factory


def register_subscriber_type(
    type_name: str,
    factory: Callable[[dict[str, Any]], EventSubscriber],
) -> None:
    """Register a custom subscriber type factory.

    After registration, the type can be used in config::

        sys_modules:
          events:
            subscribers:
              - type: "my_custom_type"
                key: value

    Args:
        type_name: Subscriber type identifier used in config ``type`` field.
        factory: Callable that receives the subscriber config dict and returns
                 an EventSubscriber instance.
    """
    _subscriber_factories[type_name] = factory


def unregister_subscriber_type(type_name: str) -> None:
    """Remove a previously registered subscriber type.

    Built-in types (``webhook``, ``a2a``) can also be removed if desired.

    Args:
        type_name: Subscriber type identifier to remove.

    Raises:
        KeyError: If the type_name is not registered.
    """
    del _subscriber_factories[type_name]


def reset_subscriber_registry() -> None:
    """Reset the subscriber registry to built-in types only.

    Useful in tests to ensure isolation between test cases that
    register custom subscriber types.
    """
    _subscriber_factories.clear()
    _subscriber_factories["webhook"] = _default_webhook_factory
    _subscriber_factories["a2a"] = _default_a2a_factory


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

    error_history = _create_error_history(config)
    result["error_history"] = error_history

    eh_middleware = ErrorHistoryMiddleware(error_history)
    executor.use(eh_middleware)
    result["error_history_middleware"] = eh_middleware

    # Usage tracking
    usage_collector = UsageCollector()
    result["usage_collector"] = usage_collector
    usage_middleware = UsageMiddleware(usage_collector)
    executor.use(usage_middleware)
    result["usage_middleware"] = usage_middleware

    _register_sys_modules(registry, config, metrics_collector, error_history, usage_collector)

    if config.get("sys_modules.events.enabled", False):
        _setup_events(registry, executor, config, metrics_collector, error_history, usage_collector, result)

    return result


def _create_error_history(config: Config) -> ErrorHistory:
    """Create an ErrorHistory instance from config values."""
    max_per_module = config.get("sys_modules.error_history.max_entries_per_module", 50)
    max_total = config.get("sys_modules.error_history.max_total_entries", 1000)
    return ErrorHistory(
        max_entries_per_module=max_per_module,
        max_total_entries=max_total,
    )


def _register_sys_module(registry: Registry, module_id: str, module: Any) -> None:
    """Register a sys module, bypassing reserved word checks.

    System modules use the 'system.' prefix which is a reserved word.
    This helper uses the public register_internal() API.
    """
    registry.register_internal(module_id, module)


def _register_sys_modules(
    registry: Registry,
    config: Config,
    metrics_collector: MetricsCollector | None,
    error_history: ErrorHistory,
    usage_collector: UsageCollector,
) -> None:
    """Register all sys.* modules: health, manifest, and usage."""
    # Health modules
    health_summary = HealthSummaryModule(
        registry=registry,
        metrics_collector=metrics_collector,
        error_history=error_history,
        config=config,
    )
    _register_sys_module(registry, "system.health.summary", health_summary)

    health_module = HealthModuleModule(
        registry=registry,
        metrics_collector=metrics_collector,
        error_history=error_history,
    )
    _register_sys_module(registry, "system.health.module", health_module)

    # Manifest modules
    manifest_module = ManifestModuleModule(
        registry=registry,
        config=config,
    )
    _register_sys_module(registry, "system.manifest.module", manifest_module)

    manifest_full = ManifestFullModule(
        registry=registry,
        config=config,
    )
    _register_sys_module(registry, "system.manifest.full", manifest_full)

    # Usage modules
    usage_summary = UsageSummaryModule(collector=usage_collector)
    _register_sys_module(registry, "system.usage.summary", usage_summary)

    usage_module = UsageModuleModule(
        registry=registry,
        usage_collector=usage_collector,
    )
    _register_sys_module(registry, "system.usage.module", usage_module)


def _setup_events(
    registry: Registry,
    executor: Executor,
    config: Config,
    metrics_collector: MetricsCollector | None,
    error_history: ErrorHistory,
    usage_collector: UsageCollector,
    result: dict[str, Any],
) -> None:
    """Set up event emitter, subscribers, PlatformNotifyMiddleware, control modules, and registry bridge."""
    event_emitter = EventEmitter()
    result["event_emitter"] = event_emitter

    error_rate_threshold = config.get("sys_modules.events.thresholds.error_rate", 0.1)
    latency_p99_threshold = config.get("sys_modules.events.thresholds.latency_p99_ms", 5000.0)
    pn_middleware = PlatformNotifyMiddleware(
        event_emitter=event_emitter,
        metrics_collector=metrics_collector,
        error_rate_threshold=error_rate_threshold,
        latency_p99_threshold_ms=latency_p99_threshold,
    )
    executor.use(pn_middleware)
    result["platform_notify_middleware"] = pn_middleware

    # Control modules (require EventEmitter)
    _register_control_modules(registry, config, event_emitter)

    _instantiate_subscribers(config, event_emitter)
    _bridge_registry_events(registry, event_emitter)


def _register_control_modules(
    registry: Registry,
    config: Config,
    event_emitter: EventEmitter,
) -> None:
    """Register control sys modules that require an EventEmitter."""
    update_config = UpdateConfigModule(config=config, event_emitter=event_emitter)
    _register_sys_module(registry, "system.control.update_config", update_config)

    reload_module = ReloadModuleModule(registry=registry, event_emitter=event_emitter)
    _register_sys_module(registry, "system.control.reload_module", reload_module)

    toggle_feature = ToggleFeatureModule(registry=registry, event_emitter=event_emitter)
    _register_sys_module(registry, "system.control.toggle_feature", toggle_feature)


def _instantiate_subscribers(config: Config, event_emitter: EventEmitter) -> None:
    """Create and subscribe EventSubscribers from config."""
    subscribers_config = config.get("sys_modules.events.subscribers", [])
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


def _create_subscriber(sub_cfg: dict[str, Any]) -> EventSubscriber:
    """Factory for EventSubscriber from a config dict.

    Looks up the subscriber type in the extensible subscriber registry.
    Use ``register_subscriber_type()`` to add custom types.

    Args:
        sub_cfg: Subscriber configuration with 'type' key.

    Returns:
        An EventSubscriber instance.

    Raises:
        ValueError: If subscriber type is not registered.
    """
    sub_type = sub_cfg.get("type", "")
    factory = _subscriber_factories.get(sub_type)
    if factory is None:
        registered = ", ".join(sorted(_subscriber_factories.keys()))
        raise ValueError(
            f"Unknown subscriber type: {sub_type!r}. "
            f"Registered types: [{registered}]. "
            f"Use register_subscriber_type() to add custom types."
        )
    return factory(sub_cfg)


def _bridge_registry_events(registry: Registry, emitter: EventEmitter) -> None:
    """Bridge registry register/unregister events to the EventEmitter."""

    def on_register(module_id: str, module: Any) -> None:
        emitter.emit(
            ApCoreEvent(
                event_type="module_registered",
                module_id=module_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="info",
                data={},
            )
        )

    def on_unregister(module_id: str, module: Any) -> None:
        emitter.emit(
            ApCoreEvent(
                event_type="module_unregistered",
                module_id=module_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="info",
                data={},
            )
        )

    registry.on("register", on_register)
    registry.on("unregister", on_unregister)
