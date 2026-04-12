"""system.control sys modules -- runtime config updates (F11), hot-reload (F10), toggle (F19)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from apcore.config import Config, _CONSTRAINTS
from apcore.errors import (
    ConfigError,
    InvalidInputError,
    ModuleDisabledError,
    ModuleError,
    ModuleNotFoundError,
    ReloadFailedError,
)
from apcore.events.emitter import ApCoreEvent, EventEmitter
from apcore.module import ModuleAnnotations
from apcore.registry.registry import Registry

__all__ = [
    "UpdateConfigModule",
    "ReloadModuleModule",
    "ToggleFeatureModule",
]

# ---------------------------------------------------------------------------
# Toggle feature state — shared across ToggleFeatureModule instances
# ---------------------------------------------------------------------------


class ToggleState:
    """Thread-safe toggle state container.

    Can be shared across ToggleFeatureModule instances or isolated per-Registry.
    State survives module reload since it lives outside the Registry.
    """

    def __init__(self) -> None:
        self._disabled: set[str] = set()
        self._lock = threading.Lock()

    def is_disabled(self, module_id: str) -> bool:
        """Check if a module is disabled."""
        with self._lock:
            return module_id in self._disabled

    def disable(self, module_id: str) -> None:
        """Mark a module as disabled."""
        with self._lock:
            self._disabled.add(module_id)

    def enable(self, module_id: str) -> None:
        """Mark a module as enabled."""
        with self._lock:
            self._disabled.discard(module_id)

    def clear(self) -> None:
        """Clear all toggle state (useful for testing)."""
        with self._lock:
            self._disabled.clear()


# Default global instance for backward compatibility
_default_toggle_state = ToggleState()


def is_module_disabled(module_id: str) -> bool:
    """Check if a module is disabled using the default toggle state. Thread-safe."""
    return _default_toggle_state.is_disabled(module_id)


def check_module_disabled(module_id: str) -> None:
    """Raise ModuleDisabledError if the module is disabled."""
    if is_module_disabled(module_id):
        raise ModuleDisabledError(module_id=module_id)


logger = logging.getLogger(__name__)

#: Keys that cannot be changed at runtime.
_RESTRICTED_KEYS: frozenset[str] = frozenset({"sys_modules.enabled"})


class UpdateConfigModule:
    """Update a runtime configuration value by dot-path key.

    Changes are runtime-only and not persisted to YAML.
    """

    description = "Update a runtime configuration value by dot-path key"
    annotations = ModuleAnnotations(requires_approval=True, destructive=False)
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Dot-path config key"},
            "value": {"description": "New value"},
            "reason": {"type": "string", "description": "Audit reason"},
        },
        "required": ["key", "value", "reason"],
    }
    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the update succeeded"},
            "key": {"type": "string", "description": "Updated config key"},
            "old_value": {"description": "Previous value (redacted for sensitive keys)"},
            "new_value": {"description": "New value (redacted for sensitive keys)"},
        },
        "required": ["success", "key", "old_value", "new_value"],
    }

    def __init__(
        self,
        config: Config,
        event_emitter: EventEmitter,
    ) -> None:
        self._config = config
        self._emitter = event_emitter

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        """Update a config value and emit a config_changed event.

        Args:
            inputs: Must contain ``key`` (dot-path str), ``value`` (any),
                    and ``reason`` (str, required for audit).
            context: Execution context (unused).

        Returns:
            Dict with ``success``, ``key``, ``old_value``, ``new_value``.
        """
        key, value, reason = self._validate_inputs(inputs)
        self._check_restricted(key)

        old_value = self._config.get(key)
        self._config.set(key, value)

        if not self._validate_post_set(key, value, old_value):
            return {}  # unreachable; _validate_post_set raises on failure

        self._emit_event(key, old_value, value)
        self._log_change(key, old_value, value, reason)

        redacted = self._is_sensitive_key(key)
        return {
            "success": True,
            "key": key,
            "old_value": "***" if redacted else old_value,
            "new_value": "***" if redacted else value,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(inputs: dict[str, Any]) -> tuple[str, Any, str]:
        """Validate and extract key, value, reason from inputs."""
        key: str = inputs.get("key", "")
        if not key:
            raise InvalidInputError(message="'key' is required and must not be empty")

        reason: str = inputs.get("reason", "")
        if not reason:
            raise InvalidInputError(message="'reason' is required and must not be empty")

        value: Any = inputs.get("value")
        return key, value, reason

    @staticmethod
    def _check_restricted(key: str) -> None:
        """Raise if key is in the restricted keys list."""
        if key in _RESTRICTED_KEYS:
            raise ModuleError(
                code="CONFIG_KEY_RESTRICTED",
                message=f"Configuration key '{key}' cannot be changed at runtime",
                details={"key": key},
            )

    def _validate_post_set(self, key: str, value: Any, old_value: Any) -> bool:
        """Check constraints after setting. Roll back on failure."""
        if key not in _CONSTRAINTS:
            return True

        check_fn, err_msg = _CONSTRAINTS[key]
        if not check_fn(value):
            self._config.set(key, old_value)
            raise ConfigError(
                message=f"Invalid value for '{key}': {err_msg} (got {value!r})",
                details={"key": key, "value": value},
            )
        return True

    def _emit_event(self, key: str, old_value: Any, new_value: Any) -> None:
        """Emit ``apcore.config.updated`` (canonical event)."""
        redacted = self._is_sensitive_key(key)
        self._emitter.emit(
            ApCoreEvent(
                event_type="apcore.config.updated",
                module_id="system.control.update_config",
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="info",
                data={
                    "key": key,
                    "old_value": "***" if redacted else old_value,
                    "new_value": "***" if redacted else new_value,
                },
            )
        )

    _SENSITIVE_SEGMENTS = ("token", "secret", "key", "password", "auth", "credential")

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        """Check if a config key path contains sensitive-sounding segments.

        Matches exact segments or underscore-compound segments (e.g. api_key,
        auth_token) without false-positives on words like "keyboard".
        """
        return any(
            seg == s or seg.endswith(f"_{s}") or seg.startswith(f"{s}_")
            for seg in key.lower().split(".")
            for s in cls._SENSITIVE_SEGMENTS
        )

    @classmethod
    def _log_change(cls, key: str, old_value: Any, new_value: Any, reason: str) -> None:
        """Log the configuration change at INFO level for audit."""
        if cls._is_sensitive_key(key):
            logger.info(
                "Config updated: key=%s old_value=*** new_value=*** reason=%s",
                key,
                reason,
            )
        else:
            logger.info(
                "Config updated: key=%s old_value=%s new_value=%s reason=%s",
                key,
                old_value,
                new_value,
                reason,
            )


class ReloadModuleModule:
    """Hot-reload a module via safe unregister + re-discover (PRD F10).

    Safely unregisters a module with drain, re-discovers its source,
    re-registers it, and emits a config_changed event on success.
    """

    description = "Hot-reload a module by safe unregister and re-discover"
    annotations = ModuleAnnotations(requires_approval=True, destructive=False)
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "module_id": {"type": "string", "description": "ID of the module to reload"},
            "reason": {"type": "string", "description": "Audit reason for the reload"},
        },
        "required": ["module_id", "reason"],
    }
    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the reload succeeded"},
            "module_id": {"type": "string", "description": "ID of the reloaded module"},
            "previous_version": {"type": "string", "description": "Version before reload"},
            "new_version": {"type": "string", "description": "Version after reload"},
            "reload_duration_ms": {"type": "number", "description": "Reload duration in milliseconds"},
        },
        "required": ["success", "module_id"],
    }

    def __init__(
        self,
        registry: Registry,
        event_emitter: EventEmitter,
    ) -> None:
        self._registry = registry
        self._emitter = event_emitter

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        """Reload a module: unregister, re-discover, re-register.

        Args:
            inputs: Must contain ``module_id`` (str) and ``reason`` (str).
            context: Execution context (unused).

        Returns:
            Dict with ``success``, ``module_id``, ``previous_version``,
            ``new_version``, ``reload_duration_ms``.
        """
        module_id, reason = self._validate_inputs(inputs)
        previous_version = self._get_current_version(module_id)

        start = time.monotonic()

        # Suspend: capture state from old instance before unload
        old_module = self._registry.get(module_id)
        suspended_state = self._try_suspend(module_id, old_module)

        self._registry.safe_unregister(module_id)

        try:
            new_module = self._rediscover_module(module_id)
        except Exception as exc:
            raise ReloadFailedError(
                module_id=module_id,
                reason=str(exc),
            ) from exc

        self._reregister_module(module_id, new_module)

        # Resume: restore state into new instance after on_load
        if suspended_state is not None:
            self._try_resume(module_id, new_module, suspended_state)

        elapsed_ms = (time.monotonic() - start) * 1000.0

        new_version = getattr(new_module, "version", "1.0.0")
        self._emit_module_reloaded(module_id, previous_version, new_version)
        self._log_reload(module_id, previous_version, new_version, reason)

        return {
            "success": True,
            "module_id": module_id,
            "previous_version": previous_version,
            "new_version": new_version,
            "reload_duration_ms": elapsed_ms,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(inputs: dict[str, Any]) -> tuple[str, str]:
        """Validate and extract module_id and reason from inputs."""
        module_id: Any = inputs.get("module_id")
        if module_id is None or not isinstance(module_id, str):
            raise InvalidInputError(message="'module_id' is required and must be a string")
        if not module_id:
            raise InvalidInputError(message="'module_id' must not be empty")

        reason: Any = inputs.get("reason")
        if reason is None or not isinstance(reason, str) or not reason:
            raise InvalidInputError(message="'reason' is required and must be a non-empty string")

        return module_id, reason

    def _get_current_version(self, module_id: str) -> str:
        """Get the version of the currently registered module."""
        module = self._registry.get(module_id)
        if module is None:
            raise ModuleNotFoundError(module_id=module_id)
        return str(getattr(module, "version", "1.0.0"))

    def _rediscover_module(self, module_id: str) -> Any:
        """Re-discover the module source and return a new instance.

        Override or mock this in tests. The default implementation triggers
        a full registry discover pass and returns the re-registered module.
        """
        self._registry.discover()
        module = self._registry.get(module_id)
        if module is None:
            raise RuntimeError(f"Module '{module_id}' was not found after re-discovery")
        return module

    def _reregister_module(self, module_id: str, module: Any) -> None:
        """Re-register a module instance after reload.

        Uses register_internal() because the module was already validated
        during initial registration. This is safe because execute() verifies
        the module exists (via _get_current_version) before reaching this
        point — only previously-registered modules can be reloaded.
        """
        self._registry.register_internal(module_id, module)

    def _emit_module_reloaded(self, module_id: str, previous_version: str, new_version: str) -> None:
        """Emit ``apcore.module.reloaded`` (canonical event)."""
        self._emitter.emit(
            ApCoreEvent(
                event_type="apcore.module.reloaded",
                module_id=module_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="info",
                data={
                    "previous_version": previous_version,
                    "new_version": new_version,
                },
            )
        )

    @staticmethod
    def _try_suspend(module_id: str, module: Any) -> dict[str, Any] | None:
        """Call on_suspend() on the module if available. Returns state or None."""
        if not hasattr(module, "on_suspend") or not callable(module.on_suspend):
            return None
        try:
            state = module.on_suspend()
            if state is not None and not isinstance(state, dict):
                logger.warning(
                    "on_suspend() for module '%s' returned non-dict (%s); ignoring",
                    module_id,
                    type(state).__name__,
                )
                return None
            return state
        except Exception as exc:
            logger.error("on_suspend() failed for module '%s': %s", module_id, exc)
            return None

    @staticmethod
    def _try_resume(module_id: str, module: Any, state: dict[str, Any]) -> None:
        """Call on_resume() on the module if available."""
        if not hasattr(module, "on_resume") or not callable(module.on_resume):
            return
        try:
            module.on_resume(state)
        except Exception as exc:
            logger.error("on_resume() failed for module '%s': %s", module_id, exc)

    @staticmethod
    def _log_reload(module_id: str, previous_version: str, new_version: str, reason: str) -> None:
        """Log the reload at INFO level for audit."""
        logger.info(
            "Module reloaded: module_id=%s previous_version=%s new_version=%s reason=%s",
            module_id,
            previous_version,
            new_version,
            reason,
        )


class ToggleFeatureModule:
    """Disable or enable a module without unloading it from the Registry (PRD F19).

    A disabled module remains registered but calls return MODULE_DISABLED error.
    Re-enabling resumes normal operation. Toggle state survives module reload.
    """

    description = "Disable or enable a module without unloading it"
    annotations = ModuleAnnotations(requires_approval=True, destructive=False)
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "module_id": {"type": "string", "description": "ID of the module to toggle"},
            "enabled": {"type": "boolean", "description": "True to enable, false to disable"},
            "reason": {"type": "string", "description": "Audit reason for the toggle"},
        },
        "required": ["module_id", "enabled", "reason"],
    }
    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "description": "Whether the toggle succeeded"},
            "module_id": {"type": "string", "description": "ID of the toggled module"},
            "enabled": {"type": "boolean", "description": "Current enabled state"},
        },
        "required": ["success", "module_id", "enabled"],
    }

    def __init__(
        self,
        registry: Registry,
        event_emitter: EventEmitter,
        toggle_state: ToggleState | None = None,
    ) -> None:
        self._registry = registry
        self._emitter = event_emitter
        self._toggle_state = toggle_state or _default_toggle_state

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        """Toggle a module's enabled/disabled state.

        Args:
            inputs: Must contain ``module_id`` (str), ``enabled`` (bool),
                    and ``reason`` (str, required for audit).
            context: Execution context (unused).

        Returns:
            Dict with ``success``, ``module_id``, ``enabled``.
        """
        module_id, enabled, reason = self._validate_inputs(inputs)
        self._check_module_exists(module_id)
        self._apply_toggle(module_id, enabled)
        self._emit_event(module_id, enabled)
        self._log_toggle(module_id, enabled, reason)

        return {
            "success": True,
            "module_id": module_id,
            "enabled": enabled,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(inputs: dict[str, Any]) -> tuple[str, bool, str]:
        """Validate and extract module_id, enabled, reason from inputs."""
        module_id: Any = inputs.get("module_id")
        if module_id is None or not isinstance(module_id, str) or not module_id:
            raise InvalidInputError(message="'module_id' is required and must be a non-empty string")

        enabled: Any = inputs.get("enabled")
        if enabled is None or not isinstance(enabled, bool):
            raise InvalidInputError(message="'enabled' is required and must be a boolean")

        reason: Any = inputs.get("reason")
        if reason is None or not isinstance(reason, str) or not reason:
            raise InvalidInputError(message="'reason' is required and must be a non-empty string")

        return module_id, enabled, reason

    def _check_module_exists(self, module_id: str) -> None:
        """Raise ModuleNotFoundError if the module is not in the Registry."""
        if not self._registry.has(module_id):
            raise ModuleNotFoundError(module_id=module_id)

    def _apply_toggle(self, module_id: str, enabled: bool) -> None:
        """Add or remove module_id from the disabled set."""
        if enabled:
            self._toggle_state.enable(module_id)
        else:
            self._toggle_state.disable(module_id)

    def _emit_event(self, module_id: str, enabled: bool) -> None:
        """Emit ``apcore.module.toggled`` (canonical event)."""
        self._emitter.emit(
            ApCoreEvent(
                event_type="apcore.module.toggled",
                module_id=module_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="info",
                data={"enabled": enabled},
            )
        )

    @staticmethod
    def _log_toggle(module_id: str, enabled: bool, reason: str) -> None:
        """Log the toggle at INFO level for audit."""
        logger.info(
            "Module toggled: module_id=%s enabled=%s reason=%s",
            module_id,
            enabled,
            reason,
        )
