"""Tests for Config system (Algorithm A12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apcore.config import Config, _DEFAULTS
from apcore.errors import ConfigError, ConfigNotFoundError


# ---------------------------------------------------------------------------
# Backward compatibility: Config(data=...) still works
# ---------------------------------------------------------------------------


class TestConfigBackwardCompat:
    def test_positional_dict(self) -> None:
        config = Config({"executor": {"default_timeout": 5000}})
        assert config.get("executor.default_timeout") == 5000

    def test_keyword_data(self) -> None:
        config = Config(data={"executor": {"max_call_depth": 10}})
        assert config.get("executor.max_call_depth") == 10

    def test_none_data(self) -> None:
        config = Config()
        assert config.get("anything") is None

    def test_get_default(self) -> None:
        config = Config()
        assert config.get("missing.key", 42) == 42

    def test_nested_dot_path(self) -> None:
        config = Config(data={"a": {"b": {"c": 99}}})
        assert config.get("a.b.c") == 99

    def test_partial_path_returns_default(self) -> None:
        config = Config(data={"a": {"b": 1}})
        assert config.get("a.b.c", "nope") == "nope"


# ---------------------------------------------------------------------------
# Config.load() from YAML
# ---------------------------------------------------------------------------


class TestConfigLoad:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text(
            """
version: "1.0.0"
project:
  name: myproject
extensions:
  root: ./ext
schema:
  root: ./sch
acl:
  root: ./acl
  default_effect: allow
"""
        )
        # Create the directories so semantic validation passes
        (tmp_path / "ext").mkdir()
        (tmp_path / "sch").mkdir()
        (tmp_path / "acl").mkdir()
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("version") == "1.0.0"
        assert config.get("project.name") == "myproject"
        assert config.get("acl.default_effect") == "allow"

    def test_load_nonexistent_file(self) -> None:
        with pytest.raises(ConfigNotFoundError):
            Config.load("/nonexistent/path.yaml")

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("key: [unclosed bracket")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            Config.load(str(yaml_file))

    def test_load_non_dict_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError, match="must be a mapping"):
            Config.load(str(yaml_file))

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        # Empty YAML → empty dict → defaults applied, validation may warn
        config = Config.load(str(yaml_file), validate=False)
        # Defaults should be merged
        assert config.get("executor.default_timeout") == 30000

    def test_load_merges_defaults(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "partial.yaml"
        yaml_file.write_text("executor:\n  default_timeout: 5000\n")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("executor.default_timeout") == 5000
        # Defaults for fields not in file
        assert config.get("executor.max_call_depth") == 32


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestConfigEnvOverrides:
    def test_env_overrides_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text("executor:\n  default_timeout: 5000\n")
        monkeypatch.setenv("APCORE_EXECUTOR_DEFAULT__TIMEOUT", "9999")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("executor.default_timeout") == 9999

    def test_env_bool_coercion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text("{}")
        monkeypatch.setenv("APCORE_EXTENSIONS_AUTO__DISCOVER", "false")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("extensions.auto_discover") is False

    def test_env_float_coercion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text("{}")
        monkeypatch.setenv("APCORE_OBSERVABILITY_TRACING_SAMPLING__RATE", "0.5")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("observability.tracing.sampling_rate") == 0.5

    def test_env_string_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text("{}")
        monkeypatch.setenv("APCORE_PROJECT_NAME", "envproject")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("project.name") == "envproject"


# ---------------------------------------------------------------------------
# Validation (Algorithm A12)
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def _make_valid_data(self, tmp_path: Path | None = None) -> dict[str, Any]:
        return {
            "version": "1.0.0",
            "extensions": {"root": "./ext"},
            "schema": {"root": "./sch"},
            "acl": {"root": "./acl", "default_effect": "deny"},
            "project": {"name": "test"},
        }

    def test_valid_config_passes(self) -> None:
        config = Config(data=self._make_valid_data())
        config.validate()  # Should not raise

    def test_missing_required_field(self) -> None:
        data = self._make_valid_data()
        del data["version"]
        config = Config(data=data)
        with pytest.raises(ConfigError, match="Missing required field.*version"):
            config.validate()

    def test_multiple_missing_fields(self) -> None:
        config = Config(data={})
        with pytest.raises(ConfigError, match="error\\(s\\)") as exc_info:
            config.validate()
        # Should list all missing fields
        err = exc_info.value
        assert "errors" in err.details
        assert len(err.details["errors"]) >= 5  # multiple required fields

    def test_invalid_acl_default_effect(self) -> None:
        data = self._make_valid_data()
        data["acl"]["default_effect"] = "maybe"
        config = Config(data=data)
        with pytest.raises(ConfigError, match="acl.default_effect"):
            config.validate()

    def test_invalid_sampling_rate(self) -> None:
        data = self._make_valid_data()
        data["observability"] = {"tracing": {"sampling_rate": 2.0}}
        config = Config(data=data)
        with pytest.raises(ConfigError, match="sampling_rate"):
            config.validate()

    def test_invalid_max_depth(self) -> None:
        data = self._make_valid_data()
        data["extensions"]["max_depth"] = 0
        config = Config(data=data)
        with pytest.raises(ConfigError, match="max_depth"):
            config.validate()

    def test_yaml_only_strategy_missing_root(self, tmp_path: Path) -> None:
        data = self._make_valid_data()
        data["schema"]["strategy"] = "yaml_only"
        data["schema"]["root"] = str(tmp_path / "nonexistent")
        config = Config(data=data)
        with pytest.raises(ConfigError, match="yaml_only"):
            config.validate()

    def test_valid_constraints_pass(self) -> None:
        data = self._make_valid_data()
        data["observability"] = {"tracing": {"sampling_rate": 0.5}}
        data["extensions"]["max_depth"] = 8
        config = Config(data=data)
        config.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Config.set()
# ---------------------------------------------------------------------------


class TestConfigSet:
    def test_set_and_get(self) -> None:
        config = Config()
        config.set("executor.default_timeout", 5000)
        assert config.get("executor.default_timeout") == 5000

    def test_set_creates_intermediate_dicts(self) -> None:
        config = Config()
        config.set("a.b.c", 42)
        assert config.get("a.b.c") == 42


# ---------------------------------------------------------------------------
# Config.reload()
# ---------------------------------------------------------------------------


class TestConfigReload:
    def test_reload_rereads_file(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text("executor:\n  default_timeout: 1000\n")
        config = Config.load(str(yaml_file), validate=False)
        assert config.get("executor.default_timeout") == 1000

        # Modify file
        yaml_file.write_text("executor:\n  default_timeout: 9999\n")
        config.reload()
        assert config.get("executor.default_timeout") == 9999

    def test_reload_without_yaml_path_raises(self) -> None:
        config = Config(data={"a": 1})
        with pytest.raises(ConfigError, match="Cannot reload"):
            config.reload()


# ---------------------------------------------------------------------------
# Config.from_defaults()
# ---------------------------------------------------------------------------


class TestConfigFromDefaults:
    def test_has_default_values(self) -> None:
        config = Config.from_defaults()
        assert config.get("executor.default_timeout") == 30000
        assert config.get("executor.max_call_depth") == 32
        assert config.get("schema.strategy") == "native_first"

    def test_env_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APCORE_EXECUTOR_DEFAULT__TIMEOUT", "7777")
        config = Config.from_defaults()
        assert config.get("executor.default_timeout") == 7777


# ---------------------------------------------------------------------------
# Config.data property
# ---------------------------------------------------------------------------


class TestConfigData:
    def test_data_returns_copy(self) -> None:
        config = Config(data={"a": 1})
        d = config.data
        d["a"] = 999
        assert config.get("a") == 1  # Original unchanged

    def test_repr_with_yaml_path(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "apcore.yaml"
        yaml_file.write_text("{}")
        config = Config.load(str(yaml_file), validate=False)
        assert "yaml_path=" in repr(config)

    def test_repr_without_yaml_path(self) -> None:
        config = Config(data={"a": 1})
        assert "keys" in repr(config)


# ---------------------------------------------------------------------------
# sys_modules and project source fields
# ---------------------------------------------------------------------------


class TestSysModulesConfig:
    def test_config_sys_modules_enabled_default(self) -> None:
        config = Config(data=dict(_DEFAULTS))
        assert config.get("sys_modules.enabled") is False

    def test_config_sys_modules_error_history_defaults(self) -> None:
        config = Config(data=dict(_DEFAULTS))
        assert config.get("sys_modules.error_history.max_entries_per_module") == 50
        assert config.get("sys_modules.error_history.max_total_entries") == 1000

    def test_config_sys_modules_events_defaults(self) -> None:
        config = Config(data=dict(_DEFAULTS))
        assert config.get("sys_modules.events.enabled") is False
        assert config.get("sys_modules.events.thresholds.error_rate") == 0.1
        assert config.get("sys_modules.events.thresholds.latency_p99_ms") == 5000.0
        assert config.get("sys_modules.events.subscribers") == []

    def test_config_project_source_repo_default(self) -> None:
        config = Config(data=dict(_DEFAULTS))
        assert config.get("project.source_repo") is None

    def test_config_project_source_root_default(self) -> None:
        config = Config(data=dict(_DEFAULTS))
        assert config.get("project.source_root") == ""

    def test_config_sys_modules_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = "sys_modules:\n  enabled: true\nversion: '0.8.0'\nextensions:\n  root: ./extensions\nschema:\n  root: ./schemas\nacl:\n  root: ./acl\n  default_effect: deny\nproject:\n  name: test"
        config_file = tmp_path / "apcore.yaml"
        config_file.write_text(yaml_content)
        config = Config.load(str(config_file), validate=False)
        assert config.get("sys_modules.enabled") is True

    def test_config_sys_modules_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APCORE_SYS__MODULES_ENABLED", "true")
        config = Config.from_defaults()
        assert config.get("sys_modules.enabled") is True

    def test_config_project_source_repo_yaml(self, tmp_path: Path) -> None:
        yaml_content = "project:\n  name: test\n  source_repo: 'https://github.com/org/repo'\nversion: '0.8.0'\nextensions:\n  root: ./extensions\nschema:\n  root: ./schemas\nacl:\n  root: ./acl\n  default_effect: deny"
        config_file = tmp_path / "apcore.yaml"
        config_file.write_text(yaml_content)
        config = Config.load(str(config_file), validate=False)
        assert config.get("project.source_repo") == "https://github.com/org/repo"

    def test_config_project_source_root_yaml(self, tmp_path: Path) -> None:
        yaml_content = "project:\n  name: test\n  source_root: 'src/modules'\nversion: '0.8.0'\nextensions:\n  root: ./extensions\nschema:\n  root: ./schemas\nacl:\n  root: ./acl\n  default_effect: deny"
        config_file = tmp_path / "apcore.yaml"
        config_file.write_text(yaml_content)
        config = Config.load(str(config_file), validate=False)
        assert config.get("project.source_root") == "src/modules"
