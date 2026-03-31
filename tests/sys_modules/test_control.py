"""Tests for system.control sys modules (update_config, reload_module, toggle_feature)."""

from __future__ import annotations

import logging
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apcore.config import Config
from apcore.errors import InvalidInputError, ModuleDisabledError, ModuleError, ModuleNotFoundError, ReloadFailedError
from apcore.events.emitter import ApCoreEvent, EventEmitter
from apcore.module import ModuleAnnotations
from apcore.registry.registry import Registry
from apcore.sys_modules.control import (
    UpdateConfigModule,
    ToggleFeatureModule,
    _default_toggle_state,
    check_module_disabled,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides: Any) -> Config:
    """Create a Config with defaults and optional overrides."""
    config = Config.from_defaults()
    for key, value in overrides.items():
        config.set(key, value)
    return config


def _make_module(
    config: Config | None = None,
    emitter: EventEmitter | None = None,
) -> UpdateConfigModule:
    """Create an UpdateConfigModule with sensible defaults."""
    if config is None:
        config = Config.from_defaults()
    if emitter is None:
        emitter = EventEmitter()
    return UpdateConfigModule(config=config, event_emitter=emitter)


# ---------------------------------------------------------------------------
# Tests: update_config
# ---------------------------------------------------------------------------


class TestUpdateConfigSuccess:
    def test_update_config_success(self) -> None:
        """Update a valid key; verify output contains success=True, key, old_value, new_value."""
        config = _make_config()
        mod = _make_module(config=config)
        result = mod.execute(
            {"key": "executor.default_timeout", "value": 5000, "reason": "testing"},
            None,
        )
        assert result["success"] is True
        assert result["key"] == "executor.default_timeout"
        assert result["old_value"] == 30000
        assert result["new_value"] == 5000


class TestUpdateConfigReturnsOldValue:
    def test_update_config_returns_old_value(self) -> None:
        """Verify old_value reflects the value before the update."""
        config = _make_config()
        original = config.get("executor.default_timeout")
        mod = _make_module(config=config)
        result = mod.execute(
            {"key": "executor.default_timeout", "value": 9999, "reason": "test"},
            None,
        )
        assert result["old_value"] == original


class TestUpdateConfigAppliesChange:
    def test_update_config_applies_change(self) -> None:
        """After update, verify Config.get(key) returns the new value."""
        config = _make_config()
        mod = _make_module(config=config)
        mod.execute(
            {"key": "executor.default_timeout", "value": 7777, "reason": "apply"},
            None,
        )
        assert config.get("executor.default_timeout") == 7777


class TestUpdateConfigEmitsConfigChangedEvent:
    def test_update_config_emits_config_changed_event(self) -> None:
        """Verify EventEmitter.emit() is called with canonical and legacy events."""
        config = _make_config()
        emitter = EventEmitter()
        emitter.emit = MagicMock()  # type: ignore[method-assign]
        mod = _make_module(config=config, emitter=emitter)
        mod.execute(
            {"key": "executor.default_timeout", "value": 5000, "reason": "event test"},
            None,
        )
        # Two events: canonical (apcore.config.updated) + legacy alias (config_changed)
        assert emitter.emit.call_count == 2
        events = [call[0][0] for call in emitter.emit.call_args_list]
        event_types = {e.event_type for e in events}
        assert "apcore.config.updated" in event_types
        assert "config_changed" in event_types
        canonical = next(e for e in events if e.event_type == "apcore.config.updated")
        assert canonical.data["key"] == "executor.default_timeout"
        assert canonical.data["old_value"] == 30000
        assert canonical.data["new_value"] == 5000


class TestUpdateConfigRestrictedKeySysModulesEnabled:
    def test_update_config_restricted_key_sys_modules_enabled(self) -> None:
        """Attempt to update sys_modules.enabled; verify CONFIG_KEY_RESTRICTED error."""
        mod = _make_module()
        with pytest.raises(ModuleError) as exc_info:
            mod.execute(
                {"key": "sys_modules.enabled", "value": True, "reason": "restricted"},
                None,
            )
        assert exc_info.value.code == "CONFIG_KEY_RESTRICTED"


class TestUpdateConfigInvalidValueRejected:
    def test_update_config_invalid_value_rejected(self) -> None:
        """Set a value that fails constraint validation; verify error and rollback."""
        config = _make_config()
        original = config.get("executor.default_timeout")
        mod = _make_module(config=config)
        with pytest.raises(ModuleError) as exc_info:
            mod.execute(
                {"key": "executor.default_timeout", "value": -1, "reason": "bad value"},
                None,
            )
        assert exc_info.value.code == "CONFIG_INVALID"
        # Value should be rolled back
        assert config.get("executor.default_timeout") == original


class TestUpdateConfigAuditLogging:
    def test_update_config_audit_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify INFO-level log contains key, old_value, new_value, and reason."""
        config = _make_config()
        mod = _make_module(config=config)
        with caplog.at_level(logging.INFO):
            mod.execute(
                {"key": "executor.default_timeout", "value": 5000, "reason": "audit test"},
                None,
            )
        log_text = caplog.text
        assert "executor.default_timeout" in log_text
        assert "30000" in log_text
        assert "5000" in log_text
        assert "audit test" in log_text


class TestUpdateConfigInputValidationMissingKey:
    def test_update_config_input_validation_missing_key(self) -> None:
        """Verify error when key is empty or missing."""
        mod = _make_module()
        with pytest.raises(InvalidInputError):
            mod.execute({"key": "", "value": 1, "reason": "test"}, None)
        with pytest.raises(InvalidInputError):
            mod.execute({"value": 1, "reason": "test"}, None)


class TestUpdateConfigInputValidationMissingReason:
    def test_update_config_input_validation_missing_reason(self) -> None:
        """Verify error when reason is empty or missing."""
        mod = _make_module()
        with pytest.raises(InvalidInputError):
            mod.execute(
                {"key": "executor.default_timeout", "value": 1, "reason": ""},
                None,
            )
        with pytest.raises(InvalidInputError):
            mod.execute(
                {"key": "executor.default_timeout", "value": 1},
                None,
            )


class TestUpdateConfigAnnotations:
    def test_update_config_annotations(self) -> None:
        """Verify module annotations include requires_approval=true and destructive=false."""
        mod = _make_module()
        assert mod.annotations.requires_approval is True
        assert mod.annotations.destructive is False


class TestUpdateConfigRuntimeOnlyNotPersisted:
    def test_update_config_runtime_only_not_persisted(self, tmp_path: Any) -> None:
        """Verify no file write occurs (Config YAML file is not modified)."""
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text(
            "version: '0.8.0'\nextensions:\n  root: ./extensions\nschema:\n  root: ./schemas\n"
            "acl:\n  root: ./acl\n  default_effect: deny\nproject:\n  name: test\n"
            "executor:\n  default_timeout: 30000\n  global_timeout: 60000\n  max_call_depth: 32\n  max_module_repeat: 3\n"
        )
        original_content = yaml_file.read_text()
        config = Config.load(str(yaml_file), validate=False)
        mod = _make_module(config=config)
        mod.execute(
            {"key": "executor.default_timeout", "value": 9999, "reason": "no persist"},
            None,
        )
        assert yaml_file.read_text() == original_content


class TestUpdateConfigDotPathNestedKey:
    def test_update_config_dot_path_nested_key(self) -> None:
        """Update a nested config key like observability.metrics.enabled."""
        config = _make_config()
        mod = _make_module(config=config)
        result = mod.execute(
            {"key": "observability.metrics.enabled", "value": True, "reason": "enable metrics"},
            None,
        )
        assert result["success"] is True
        assert result["old_value"] is False
        assert result["new_value"] is True
        assert config.get("observability.metrics.enabled") is True


# ---------------------------------------------------------------------------
# Helpers for reload_module tests
# ---------------------------------------------------------------------------


class _FakeModule:
    """Minimal module stub for reload testing."""

    version = "1.0.0"
    description = "fake module"

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        return {}


class _FakeModuleV2:
    """Updated version of the fake module."""

    version = "2.0.0"
    description = "fake module v2"

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        return {}


def _make_registry_with_module(module_id: str = "my.module") -> tuple[Registry, _FakeModule]:
    """Create a registry with a single fake module registered."""
    registry = Registry()
    module = _FakeModule()
    with registry._lock:
        registry._modules[module_id] = module
        registry._lowercase_map[module_id.lower()] = module_id
    return registry, module


def _make_reload_module(
    registry: Registry | None = None,
    emitter: EventEmitter | None = None,
) -> Any:
    """Create a ReloadModuleModule with sensible defaults."""
    from apcore.sys_modules.control import ReloadModuleModule

    if registry is None:
        registry = Registry()
    if emitter is None:
        emitter = EventEmitter()
    return ReloadModuleModule(registry=registry, event_emitter=emitter)


# ---------------------------------------------------------------------------
# Tests: reload_module
# ---------------------------------------------------------------------------


class TestReloadModuleSuccess:
    def test_reload_module_success(self) -> None:
        """Reload an existing module; verify output contains expected fields."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        new_module = _FakeModuleV2()
        with patch.object(mod, "_rediscover_module", return_value=new_module):
            result = mod.execute(
                {"module_id": "my.module", "reason": "testing reload"},
                context=None,
            )

        assert result["success"] is True
        assert result["module_id"] == "my.module"
        assert result["previous_version"] == "1.0.0"
        assert result["new_version"] == "2.0.0"
        assert "reload_duration_ms" in result
        assert isinstance(result["reload_duration_ms"], float)


class TestReloadModuleNotFound:
    def test_reload_module_not_found(self) -> None:
        """Attempt to reload a non-existent module_id; verify MODULE_NOT_FOUND error."""
        mod = _make_reload_module()

        with pytest.raises(ModuleNotFoundError) as exc_info:
            mod.execute(
                {"module_id": "nonexistent.module", "reason": "test"},
                context=None,
            )
        assert exc_info.value.code == "MODULE_NOT_FOUND"


class TestReloadModuleCallsSafeUnregister:
    def test_reload_module_calls_safe_unregister(self) -> None:
        """Verify Registry.safe_unregister() is called with the correct module_id."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        new_module = _FakeModuleV2()
        with (
            patch.object(registry, "safe_unregister", return_value=True) as mock_unreg,
            patch.object(mod, "_rediscover_module", return_value=new_module),
        ):
            mod.execute(
                {"module_id": "my.module", "reason": "test"},
                context=None,
            )

        mock_unreg.assert_called_once_with("my.module")


class TestReloadModuleCallsDiscover:
    def test_reload_module_calls_discover(self) -> None:
        """Verify the module file is re-discovered after unregistration."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        new_module = _FakeModuleV2()
        with patch.object(mod, "_rediscover_module", return_value=new_module) as mock_discover:
            mod.execute(
                {"module_id": "my.module", "reason": "test"},
                context=None,
            )

        mock_discover.assert_called_once_with("my.module")


class TestReloadModuleCallsRegister:
    def test_reload_module_calls_register(self) -> None:
        """Verify the module is re-registered after re-discovery."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        new_module = _FakeModuleV2()
        with patch.object(mod, "_rediscover_module", return_value=new_module):
            mod.execute(
                {"module_id": "my.module", "reason": "test"},
                context=None,
            )

        assert registry.has("my.module")
        registered = registry.get("my.module")
        assert registered is new_module


class TestReloadModuleEmitsConfigChangedEvent:
    def test_reload_module_emits_config_changed_event(self) -> None:
        """Verify EventEmitter.emit() is called with a config_changed event."""
        registry, _ = _make_registry_with_module("my.module")
        emitter = EventEmitter()
        mod = _make_reload_module(registry=registry, emitter=emitter)

        new_module = _FakeModuleV2()
        with (
            patch.object(emitter, "emit") as mock_emit,
            patch.object(mod, "_rediscover_module", return_value=new_module),
        ):
            mod.execute(
                {"module_id": "my.module", "reason": "test"},
                context=None,
            )

        # Two events: canonical (apcore.module.reloaded) + legacy alias (config_changed)
        assert mock_emit.call_count == 2
        events = [call[0][0] for call in mock_emit.call_args_list]
        assert all(isinstance(e, ApCoreEvent) for e in events)
        event_types = {e.event_type for e in events}
        assert "apcore.module.reloaded" in event_types
        assert "config_changed" in event_types
        canonical = next(e for e in events if e.event_type == "apcore.module.reloaded")
        assert canonical.module_id == "my.module"


class TestReloadModuleNoEventOnFailure:
    def test_reload_module_no_event_on_failure(self) -> None:
        """Verify no event is emitted when reload fails."""
        registry, _ = _make_registry_with_module("my.module")
        emitter = EventEmitter()
        mod = _make_reload_module(registry=registry, emitter=emitter)

        with (
            patch.object(emitter, "emit") as mock_emit,
            patch.object(mod, "_rediscover_module", side_effect=RuntimeError("discover failed")),
        ):
            with pytest.raises(ReloadFailedError):
                mod.execute(
                    {"module_id": "my.module", "reason": "test"},
                    context=None,
                )

        mock_emit.assert_not_called()


class TestReloadModuleReloadFailedError:
    def test_reload_module_reload_failed_error(self) -> None:
        """Simulate re-discover failure; verify RELOAD_FAILED error with descriptive message."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        with patch.object(mod, "_rediscover_module", side_effect=RuntimeError("file not found")):
            with pytest.raises(ReloadFailedError) as exc_info:
                mod.execute(
                    {"module_id": "my.module", "reason": "test"},
                    context=None,
                )

        assert exc_info.value.code == "RELOAD_FAILED"
        assert "my.module" in exc_info.value.message


class TestReloadModuleInputValidation:
    def test_reload_module_input_validation_missing_module_id(self) -> None:
        """Verify module_id is required."""
        mod = _make_reload_module()

        with pytest.raises(InvalidInputError):
            mod.execute({"reason": "test"}, context=None)

    def test_reload_module_input_validation_missing_reason(self) -> None:
        """Verify reason is required."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        with pytest.raises(InvalidInputError):
            mod.execute({"module_id": "my.module"}, context=None)

    def test_reload_module_input_validation_non_string_module_id(self) -> None:
        """Verify module_id must be a string."""
        mod = _make_reload_module()

        with pytest.raises(InvalidInputError):
            mod.execute({"module_id": 123, "reason": "test"}, context=None)


class TestReloadModuleAnnotations:
    def test_reload_module_annotations(self) -> None:
        """Verify module annotations include requires_approval=true and destructive=false."""
        mod = _make_reload_module()

        assert hasattr(mod, "annotations")
        annotations = mod.annotations
        assert isinstance(annotations, ModuleAnnotations)
        assert annotations.requires_approval is True
        assert annotations.destructive is False


class TestReloadModuleAuditIncludesReason:
    def test_reload_module_audit_includes_reason(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify the reason parameter is logged at INFO level for audit trail."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        new_module = _FakeModuleV2()
        with caplog.at_level(logging.INFO), patch.object(mod, "_rediscover_module", return_value=new_module):
            mod.execute(
                {"module_id": "my.module", "reason": "scheduled maintenance"},
                context=None,
            )

        assert any("scheduled maintenance" in msg for msg in caplog.messages)


class TestReloadModuleDurationTracking:
    def test_reload_module_duration_tracking(self) -> None:
        """Verify reload_duration_ms reflects actual elapsed time (not zero)."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_reload_module(registry=registry)

        def slow_discover(module_id: str) -> _FakeModuleV2:
            time.sleep(0.01)  # 10ms delay
            return _FakeModuleV2()

        with patch.object(mod, "_rediscover_module", side_effect=slow_discover):
            result = mod.execute(
                {"module_id": "my.module", "reason": "test"},
                context=None,
            )

        assert result["reload_duration_ms"] > 0.0


# ---------------------------------------------------------------------------
# Helpers for toggle_feature tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def _clear_disabled_modules() -> Any:
    """Ensure the disabled modules set is clean before and after each toggle test."""
    _default_toggle_state.clear()
    yield
    _default_toggle_state.clear()


def _make_toggle_module(
    registry: Registry | None = None,
    emitter: EventEmitter | None = None,
) -> ToggleFeatureModule:
    """Create a ToggleFeatureModule with sensible defaults."""
    if registry is None:
        registry = Registry()
    if emitter is None:
        emitter = EventEmitter()
    return ToggleFeatureModule(registry=registry, event_emitter=emitter)


# ---------------------------------------------------------------------------
# Tests: toggle_feature
# ---------------------------------------------------------------------------


class TestToggleFeatureDisableSuccess:
    def test_toggle_feature_disable_success(self, _clear_disabled_modules: Any) -> None:
        """Disable an existing module; verify output contains success=True, module_id, enabled=False."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        result = mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "maintenance"},
            context=None,
        )
        assert result["success"] is True
        assert result["module_id"] == "my.module"
        assert result["enabled"] is False


class TestToggleFeatureEnableSuccess:
    def test_toggle_feature_enable_success(self, _clear_disabled_modules: Any) -> None:
        """Re-enable a disabled module; verify enabled=True."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        # Disable first
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "disable"},
            context=None,
        )
        # Re-enable
        result = mod.execute(
            {"module_id": "my.module", "enabled": True, "reason": "re-enable"},
            context=None,
        )
        assert result["success"] is True
        assert result["enabled"] is True


class TestToggleFeatureDisabledModuleReturnsError:
    def test_toggle_feature_disabled_module_returns_error(self, _clear_disabled_modules: Any) -> None:
        """After disabling, call the disabled module; verify MODULE_DISABLED error."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "test"},
            context=None,
        )
        with pytest.raises(ModuleDisabledError) as exc_info:
            check_module_disabled("my.module")
        assert exc_info.value.code == "MODULE_DISABLED"


class TestToggleFeatureEnabledModuleResumes:
    def test_toggle_feature_enabled_module_resumes(self, _clear_disabled_modules: Any) -> None:
        """After re-enabling, call the module; verify it executes normally."""
        registry, module = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        # Disable
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "disable"},
            context=None,
        )
        # Re-enable
        mod.execute(
            {"module_id": "my.module", "enabled": True, "reason": "re-enable"},
            context=None,
        )
        # Should not raise
        check_module_disabled("my.module")
        # Module should execute normally
        result = module.execute({}, None)
        assert result == {}


class TestToggleFeatureModuleNotFound:
    def test_toggle_feature_module_not_found(self, _clear_disabled_modules: Any) -> None:
        """Attempt to toggle a non-existent module_id; verify MODULE_NOT_FOUND error."""
        mod = _make_toggle_module()
        with pytest.raises(ModuleNotFoundError) as exc_info:
            mod.execute(
                {"module_id": "nonexistent.module", "enabled": False, "reason": "test"},
                context=None,
            )
        assert exc_info.value.code == "MODULE_NOT_FOUND"


class TestToggleFeatureEmitsModuleHealthChanged:
    def test_toggle_feature_emits_module_health_changed(self, _clear_disabled_modules: Any) -> None:
        """Verify emit() is called with canonical and legacy events on toggle."""
        registry, _ = _make_registry_with_module("my.module")
        emitter = EventEmitter()
        emitter.emit = MagicMock()  # type: ignore[method-assign]
        mod = _make_toggle_module(registry=registry, emitter=emitter)
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "test"},
            context=None,
        )
        # Two events: canonical (apcore.module.toggled) + legacy alias (module_health_changed)
        assert emitter.emit.call_count == 2
        events = [call[0][0] for call in emitter.emit.call_args_list]
        assert all(isinstance(e, ApCoreEvent) for e in events)
        event_types = {e.event_type for e in events}
        assert "apcore.module.toggled" in event_types
        assert "module_health_changed" in event_types
        canonical = next(e for e in events if e.event_type == "apcore.module.toggled")
        assert canonical.module_id == "my.module"
        assert canonical.data["enabled"] is False


class TestToggleFeatureSurvivesReload:
    def test_toggle_feature_survives_reload(self, _clear_disabled_modules: Any) -> None:
        """Disable a module, then reload it; verify it remains disabled after reload."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "pre-reload"},
            context=None,
        )
        # Simulate reload: unregister and re-register
        registry.unregister("my.module")
        new_module = _FakeModuleV2()
        with registry._lock:
            registry._modules["my.module"] = new_module
            registry._lowercase_map["my.module"] = "my.module"
        # Module should still be disabled (state survives reload)
        with pytest.raises(ModuleDisabledError):
            check_module_disabled("my.module")


class TestToggleFeatureAnnotations:
    def test_toggle_feature_annotations(self) -> None:
        """Verify module annotations include requires_approval=true."""
        mod = _make_toggle_module()
        assert hasattr(mod, "annotations")
        assert isinstance(mod.annotations, ModuleAnnotations)
        assert mod.annotations.requires_approval is True
        assert mod.annotations.destructive is False


class TestToggleFeatureReasonLogged:
    def test_toggle_feature_reason_logged(self, _clear_disabled_modules: Any, caplog: pytest.LogCaptureFixture) -> None:
        """Verify the reason parameter is logged at INFO level for audit trail."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        with caplog.at_level(logging.INFO):
            mod.execute(
                {"module_id": "my.module", "enabled": False, "reason": "security incident"},
                context=None,
            )
        assert any("security incident" in msg for msg in caplog.messages)


class TestToggleFeatureDisableAlreadyDisabled:
    def test_toggle_feature_disable_already_disabled(self, _clear_disabled_modules: Any) -> None:
        """Disable an already-disabled module; verify idempotent success (no error)."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "first"},
            context=None,
        )
        # Second disable should succeed without error
        result = mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "second"},
            context=None,
        )
        assert result["success"] is True
        assert result["enabled"] is False


class TestToggleFeatureEnableAlreadyEnabled:
    def test_toggle_feature_enable_already_enabled(self, _clear_disabled_modules: Any) -> None:
        """Enable an already-enabled module; verify idempotent success."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        # Module is enabled by default, enabling again should succeed
        result = mod.execute(
            {"module_id": "my.module", "enabled": True, "reason": "redundant enable"},
            context=None,
        )
        assert result["success"] is True
        assert result["enabled"] is True


class TestToggleFeatureDisabledModuleStaysInRegistry:
    def test_toggle_feature_disabled_module_stays_in_registry(self, _clear_disabled_modules: Any) -> None:
        """After disabling, verify Registry.list() still includes the module."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "test"},
            context=None,
        )
        assert "my.module" in registry.list()
        assert registry.has("my.module")


class TestToggleFeatureDisabledModuleInManifest:
    def test_toggle_feature_disabled_module_in_manifest(self, _clear_disabled_modules: Any) -> None:
        """After disabling, verify the module is still retrievable via get_definition (manifest)."""
        registry, _ = _make_registry_with_module("my.module")
        mod = _make_toggle_module(registry=registry)
        mod.execute(
            {"module_id": "my.module", "enabled": False, "reason": "test"},
            context=None,
        )
        # Module should still be accessible via get() and get_definition()
        assert registry.get("my.module") is not None
