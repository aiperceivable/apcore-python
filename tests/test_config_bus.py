"""Tests for Config Bus (§9.4–§9.15) — namespace registry, namespace mode, mounts, bind, etc."""

from __future__ import annotations

import dataclasses
import threading
from pathlib import Path
from typing import Any

import pytest

from apcore.config import (
    Config,
    _GLOBAL_NS_REGISTRY,
    _GLOBAL_NS_REGISTRY_LOCK,
)
from apcore.errors import (
    ConfigBindError,
    ConfigEnvPrefixConflictError,
    ConfigError,
    ConfigMountError,
    ConfigNamespaceDuplicateError,
    ConfigNamespaceReservedError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_ns_registry_except_builtins() -> None:
    """Remove test namespaces from the global registry (leave built-ins)."""
    with _GLOBAL_NS_REGISTRY_LOCK:
        builtin_names = {"observability", "sys_modules"}
        keys_to_remove = [k for k in _GLOBAL_NS_REGISTRY if k not in builtin_names]
        for k in keys_to_remove:
            del _GLOBAL_NS_REGISTRY[k]


def _clear_ns_registry_all() -> None:
    """Remove ALL namespaces from the global registry (including built-ins)."""
    with _GLOBAL_NS_REGISTRY_LOCK:
        _GLOBAL_NS_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Namespace registration
# ---------------------------------------------------------------------------


class TestRegisterNamespace:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_register_basic(self) -> None:
        Config.register_namespace("myns")
        names = [r["name"] for r in Config.registered_namespaces()]
        assert "myns" in names

    def test_register_with_defaults(self) -> None:
        Config.register_namespace("myns2", defaults={"foo": 1})
        namespaces = Config.registered_namespaces()
        ns = next(r for r in namespaces if r["name"] == "myns2")
        assert ns["has_schema"] is False

    def test_register_with_schema(self) -> None:
        schema = {"type": "object", "properties": {"enabled": {"type": "boolean"}}}
        Config.register_namespace("myns3", schema=schema)
        namespaces = Config.registered_namespaces()
        ns = next(r for r in namespaces if r["name"] == "myns3")
        assert ns["has_schema"] is True

    def test_register_duplicate_raises(self) -> None:
        Config.register_namespace("dupns")
        with pytest.raises(ConfigNamespaceDuplicateError):
            Config.register_namespace("dupns")

    def test_register_reserved_apcore_raises(self) -> None:
        with pytest.raises(ConfigNamespaceReservedError):
            Config.register_namespace("apcore")

    def test_register_reserved_config_raises(self) -> None:
        with pytest.raises(ConfigNamespaceReservedError):
            Config.register_namespace("_config")

    def test_register_env_prefix_conflict_legacy_pattern(self) -> None:
        # Must not match ^APCORE_[A-Z0-9]
        with pytest.raises(ConfigEnvPrefixConflictError):
            Config.register_namespace("envns", env_prefix="APCORE_FOO")

    def test_register_env_prefix_double_underscore_ok(self) -> None:
        # APCORE__SOMETHING is fine (double underscore)
        Config.register_namespace("envns2", env_prefix="APCORE__ENVNS2")
        names = [r["name"] for r in Config.registered_namespaces()]
        assert "envns2" in names

    def test_register_env_prefix_duplicate_raises(self) -> None:
        Config.register_namespace("envns3", env_prefix="MYAPP__NS3")
        with pytest.raises(ConfigEnvPrefixConflictError):
            Config.register_namespace("envns4", env_prefix="MYAPP__NS3")

    def test_registered_namespaces_returns_list_of_dicts(self) -> None:
        Config.register_namespace("listns")
        result = Config.registered_namespaces()
        assert isinstance(result, list)
        for item in result:
            assert "name" in item
            assert "env_prefix" in item
            assert "has_schema" in item


# ---------------------------------------------------------------------------
# Built-in namespace registrations (§9.15)
# ---------------------------------------------------------------------------


class TestBuiltinNamespaces:
    def test_observability_registered(self) -> None:
        names = [r["name"] for r in Config.registered_namespaces()]
        assert "observability" in names

    def test_sys_modules_registered(self) -> None:
        names = [r["name"] for r in Config.registered_namespaces()]
        assert "sys_modules" in names

    def test_observability_has_correct_env_prefix(self) -> None:
        namespaces = Config.registered_namespaces()
        ns = next(r for r in namespaces if r["name"] == "observability")
        assert ns["env_prefix"] == "APCORE__OBSERVABILITY"

    def test_sys_modules_has_correct_env_prefix(self) -> None:
        namespaces = Config.registered_namespaces()
        ns = next(r for r in namespaces if r["name"] == "sys_modules")
        assert ns["env_prefix"] == "APCORE__SYS"


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


class TestModeDetection:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_legacy_mode_when_no_apcore_key(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(
            """
version: "1.0.0"
project:
  name: test
extensions:
  root: ./ext
schema:
  root: ./sch
acl:
  root: ./acl
  default_effect: allow
"""
        )
        config = Config.load(str(yaml_file), validate=False)
        assert config._mode == "legacy"

    def test_namespace_mode_when_apcore_key_present(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(
            """
apcore:
  version: "1.0.0"
  project:
    name: test
  extensions:
    root: ./ext
  schema:
    root: ./sch
  acl:
    root: ./acl
    default_effect: allow
"""
        )
        config = Config.load(str(yaml_file), validate=False)
        assert config._mode == "namespace"


# ---------------------------------------------------------------------------
# Namespace mode: get()
# ---------------------------------------------------------------------------


class TestNamespaceModeGet:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def _make_ns_config(self, extra: dict[str, Any] | None = None, tmp_path: Path | None = None) -> Config:
        """Return a namespace-mode Config with optional extra namespaces."""
        data: dict[str, Any] = {
            "apcore": {
                "version": "1.0.0",
                "project": {"name": "test"},
                "extensions": {"root": "./ext"},
                "schema": {"root": "./sch"},
                "acl": {"root": "./acl", "default_effect": "allow"},
            }
        }
        if extra:
            data.update(extra)
        config = Config(data=data)
        config._mode = "namespace"
        return config

    def test_get_apcore_dotpath(self) -> None:
        config = self._make_ns_config()
        assert config.get("apcore.version") == "1.0.0"

    def test_get_registered_namespace_key(self) -> None:
        Config.register_namespace("plugins", defaults={"enabled": True})
        config = self._make_ns_config({"plugins": {"enabled": False, "count": 3}})
        assert config.get("plugins.count") == 3
        assert config.get("plugins.enabled") is False

    def test_get_namespace_root_returns_dict(self) -> None:
        Config.register_namespace("myapp")
        config = self._make_ns_config({"myapp": {"x": 1}})
        result = config.get("myapp")
        assert isinstance(result, dict)
        assert result["x"] == 1

    def test_get_missing_key_returns_default(self) -> None:
        config = self._make_ns_config()
        assert config.get("apcore.missing.key", "fallback") == "fallback"

    def test_get_hyphenated_namespace(self) -> None:
        Config.register_namespace("apcore-mcp")
        config = self._make_ns_config({"apcore-mcp": {"transport": "stdio"}})
        assert config.get("apcore-mcp.transport") == "stdio"


# ---------------------------------------------------------------------------
# namespace() method
# ---------------------------------------------------------------------------


class TestNamespaceMethod:
    def test_namespace_returns_deep_copy(self) -> None:
        config = Config(data={"ns": {"x": 1, "nested": {"y": 2}}})
        result = config.namespace("ns")
        assert result == {"x": 1, "nested": {"y": 2}}
        # Mutating result must not affect config
        result["x"] = 99
        assert config.namespace("ns")["x"] == 1

    def test_namespace_missing_returns_empty_dict(self) -> None:
        config = Config(data={})
        assert config.namespace("missing") == {}

    def test_namespace_non_dict_value_returns_empty_dict(self) -> None:
        config = Config(data={"bad": "not_a_dict"})
        assert config.namespace("bad") == {}


# ---------------------------------------------------------------------------
# get_typed()
# ---------------------------------------------------------------------------


class TestGetTyped:
    def test_get_typed_int(self) -> None:
        config = Config(data={"executor": {"max_call_depth": 16}})
        value = config.get_typed("executor.max_call_depth", int)
        assert value == 16
        assert isinstance(value, int)

    def test_get_typed_str_coercion(self) -> None:
        config = Config(data={"meta": {"count": 5}})
        result = config.get_typed("meta.count", str)
        assert result == "5"

    def test_get_typed_missing_raises(self) -> None:
        config = Config(data={})
        with pytest.raises(ConfigBindError):
            config.get_typed("missing.key", int)

    def test_get_typed_bad_coercion_raises(self) -> None:
        config = Config(data={"meta": {"label": "hello"}})
        with pytest.raises(ConfigBindError):
            config.get_typed("meta.label", int)


# ---------------------------------------------------------------------------
# bind()
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _PluginConfig:
    enabled: bool = True
    count: int = 0


class TestBind:
    def test_bind_dataclass(self) -> None:
        config = Config(data={"plugins": {"enabled": False, "count": 3}})
        result = config.bind("plugins", _PluginConfig)
        assert isinstance(result, _PluginConfig)
        assert result.enabled is False
        assert result.count == 3

    def test_bind_missing_namespace_returns_defaults(self) -> None:
        config = Config(data={})
        # Empty namespace → dataclass gets no kwargs → uses defaults
        result = config.bind("plugins", _PluginConfig)
        assert isinstance(result, _PluginConfig)
        assert result.enabled is True
        assert result.count == 0

    def test_bind_bad_class_raises_config_bind_error(self) -> None:
        class _Bad:
            def __init__(self, unknown_field: int) -> None:
                pass

        config = Config(data={"ns": {"x": 1}})
        with pytest.raises(ConfigBindError):
            config.bind("ns", _Bad)


# ---------------------------------------------------------------------------
# mount()
# ---------------------------------------------------------------------------


class TestMount:
    def test_mount_from_dict(self) -> None:
        config = Config(data={"ns": {"a": 1}})
        config.mount("ns", from_dict={"b": 2})
        assert config.namespace("ns") == {"a": 1, "b": 2}

    def test_mount_from_file(self, tmp_path: Path) -> None:
        mount_file = tmp_path / "extra.yaml"
        mount_file.write_text("c: 3\n")
        config = Config(data={"ns": {"a": 1}})
        config.mount("ns", from_file=str(mount_file))
        assert config.namespace("ns")["c"] == 3

    def test_mount_both_sources_raises(self) -> None:
        config = Config(data={})
        with pytest.raises(ConfigMountError):
            config.mount("ns", from_dict={"x": 1}, from_file="/some/path.yaml")

    def test_mount_no_source_raises(self) -> None:
        config = Config(data={})
        with pytest.raises(ConfigMountError):
            config.mount("ns")

    def test_mount_reserved_namespace_raises(self) -> None:
        config = Config(data={})
        with pytest.raises(ConfigMountError):
            config.mount("_config", from_dict={"x": 1})

    def test_mount_nonexistent_file_raises(self) -> None:
        config = Config(data={})
        with pytest.raises(ConfigMountError):
            config.mount("ns", from_file="/nonexistent/path.yaml")

    def test_mount_deep_merge(self) -> None:
        config = Config(data={"ns": {"nested": {"x": 1, "y": 2}}})
        config.mount("ns", from_dict={"nested": {"z": 3}})
        ns = config.namespace("ns")
        assert ns["nested"]["x"] == 1
        assert ns["nested"]["z"] == 3

    def test_mount_stored_for_reload(self, tmp_path: Path) -> None:
        """Mount data is preserved in _mounts for reload."""
        config = Config(data={"ns": {}})
        config.mount("ns", from_dict={"key": "value"})
        assert "ns" in config._mounts
        assert config._mounts["ns"]["key"] == "value"


# ---------------------------------------------------------------------------
# Namespace defaults in namespace mode
# ---------------------------------------------------------------------------


class TestNamespaceDefaults:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_defaults_applied_when_namespace_absent(self, tmp_path: Path) -> None:
        Config.register_namespace("testdefaults", defaults={"level": "info", "enabled": True})
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("apcore:\n  version: '1.0.0'\n")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("testdefaults.level") == "info"
        assert config.get("testdefaults.enabled") is True

    def test_file_data_overrides_defaults(self, tmp_path: Path) -> None:
        Config.register_namespace("testdefaults2", defaults={"level": "info"})
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("apcore:\n  version: '1.0.0'\ntestdefaults2:\n  level: debug\n")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("testdefaults2.level") == "debug"


# ---------------------------------------------------------------------------
# Namespace env overrides
# ---------------------------------------------------------------------------


class TestNamespaceEnvOverrides:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_namespace_env_override_applied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        Config.register_namespace("envtest", env_prefix="MYAPP__ENVTEST")
        monkeypatch.setenv("MYAPP__ENVTEST_LEVEL", "debug")
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("apcore:\n  version: '1.0.0'\n")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("envtest.level") == "debug"

    def test_longer_prefix_wins_over_shorter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        Config.register_namespace("ns_a", env_prefix="APP__NS")
        Config.register_namespace("ns_b", env_prefix="APP__NS_B")
        monkeypatch.setenv("APP__NS_B_KEY", "from_b")
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("apcore:\n  version: '1.0.0'\n")
        config = Config.load(str(yaml_file), validate=False)
        # APP__NS_B is longer than APP__NS, so it should match ns_b
        assert config.get("ns_b.key") == "from_b"


# ---------------------------------------------------------------------------
# A12-NS validation
# ---------------------------------------------------------------------------


class TestA12NSValidation:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_strict_mode_rejects_unknown_namespace(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(
            """
apcore:
  version: "1.0.0"
  project:
    name: test
  extensions:
    root: ./ext
  schema:
    root: ./sch
  acl:
    root: ./acl
    default_effect: allow
_config:
  strict: true
unknown_ns:
  x: 1
"""
        )
        with pytest.raises(ConfigError, match="Unknown namespace"):
            Config.load(str(yaml_file), validate=True)

    def test_non_strict_mode_allows_unknown_namespace(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(
            """
apcore:
  version: "1.0.0"
  project:
    name: test
  extensions:
    root: ./ext
  schema:
    root: ./sch
  acl:
    root: ./acl
    default_effect: allow
unknown_ns:
  x: 1
"""
        )
        # Should not raise
        config = Config.load(str(yaml_file), validate=True)
        assert config._mode == "namespace"


# ---------------------------------------------------------------------------
# Hot-reload preserves mounts
# ---------------------------------------------------------------------------


_NAMESPACE_YAML_TEMPLATE = """\
apcore:
  version: "1.0.0"
  project:
    name: test
  extensions:
    root: ./ext
  schema:
    root: ./sch
  acl:
    root: ./acl
    default_effect: allow
"""


class TestHotReload:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_reload_reapplies_mounts(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(_NAMESPACE_YAML_TEMPLATE)
        config = Config.load(str(yaml_file), validate=False)
        config.mount("plugins", from_dict={"enabled": True})
        assert config.namespace("plugins")["enabled"] is True

        config.reload()
        # Mount must survive reload
        assert config.namespace("plugins")["enabled"] is True

    def test_reload_updates_file_data(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text(_NAMESPACE_YAML_TEMPLATE)
        config = Config.load(str(yaml_file), validate=False)

        updated = _NAMESPACE_YAML_TEMPLATE.replace('version: "1.0.0"', 'version: "2.0.0"')
        yaml_file.write_text(updated)
        config.reload()
        assert config.get("apcore.version") == "2.0.0"

    def test_reload_without_yaml_path_raises(self) -> None:
        config = Config(data={"x": 1})
        with pytest.raises(ConfigError, match="Cannot reload"):
            config.reload()


# ---------------------------------------------------------------------------
# Thread-safety of register_namespace
# ---------------------------------------------------------------------------


class TestNamespaceRegistryThreadSafety:
    def setup_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def teardown_method(self) -> None:
        _clear_ns_registry_except_builtins()

    def test_concurrent_registration_only_one_succeeds(self) -> None:
        errors: list[Exception] = []
        successes: list[str] = []

        def register(i: int) -> None:
            try:
                Config.register_namespace(f"concurrent_ns_{i}")
                successes.append(f"concurrent_ns_{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == 5  # all unique names succeed
        assert not errors
