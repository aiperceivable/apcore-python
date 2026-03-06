"""Configuration loading, validation, and environment variable overrides (Algorithm A12)."""

from __future__ import annotations

import copy
import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml

from apcore.errors import ConfigError, ConfigNotFoundError

__all__ = ["Config"]

_logger = logging.getLogger(__name__)

#: Environment variable prefix for overrides.
_ENV_PREFIX = "APCORE_"

#: Required configuration fields (dot-paths).
_REQUIRED_FIELDS: tuple[str, ...] = (
    "version",
    "extensions.root",
    "schema.root",
    "acl.root",
    "acl.default_effect",
    "project.name",
)

#: Field constraints: field → (validator_fn, error_message).
_CONSTRAINTS: dict[str, tuple[Any, str]] = {
    "acl.default_effect": (
        lambda v: v in ("allow", "deny"),
        "must be 'allow' or 'deny'",
    ),
    "observability.tracing.sampling_rate": (
        lambda v: isinstance(v, (int, float)) and 0.0 <= v <= 1.0,
        "must be a number in [0.0, 1.0]",
    ),
    "extensions.max_depth": (
        lambda v: isinstance(v, int) and 1 <= v <= 16,
        "must be an integer in [1, 16]",
    ),
    "executor.default_timeout": (
        lambda v: isinstance(v, int) and v >= 0,
        "must be a non-negative integer (milliseconds)",
    ),
    "executor.global_timeout": (
        lambda v: isinstance(v, int) and v >= 0,
        "must be a non-negative integer (milliseconds)",
    ),
    "executor.max_call_depth": (
        lambda v: isinstance(v, int) and v >= 1,
        "must be a positive integer",
    ),
    "executor.max_module_repeat": (
        lambda v: isinstance(v, int) and v >= 1,
        "must be a positive integer",
    ),
}

#: Default configuration values.
_DEFAULTS: dict[str, Any] = {
    "version": "0.8.0",
    "extensions": {
        "root": "./extensions",
        "auto_discover": True,
        "max_depth": 8,
        "follow_symlinks": False,
    },
    "schema": {
        "root": "./schemas",
        "strategy": "yaml_first",
        "max_ref_depth": 32,
    },
    "acl": {
        "root": "./acl",
        "default_effect": "deny",
    },
    "executor": {
        "default_timeout": 30000,
        "global_timeout": 60000,
        "max_call_depth": 32,
        "max_module_repeat": 3,
    },
    "observability": {
        "tracing": {
            "enabled": False,
            "sampling_rate": 1.0,
        },
        "metrics": {
            "enabled": False,
        },
    },
    "project": {
        "name": "apcore",
    },
}


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _get_nested(data: dict[str, Any], dot_path: str, default: Any = None) -> Any:
    """Retrieve a value from a nested dict using a dot-separated path."""
    parts = dot_path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _set_nested(data: dict[str, Any], dot_path: str, value: Any) -> None:
    """Set a value in a nested dict, creating intermediate dicts as needed."""
    parts = dot_path.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply APCORE_* environment variable overrides.

    Naming convention: single ``_`` → ``.`` (section separator), double ``__`` → literal ``_``.

    Examples::

        APCORE_EXECUTOR_DEFAULT__TIMEOUT=5000  → executor.default_timeout = 5000
        APCORE_ACL_DEFAULT__EFFECT=allow        → acl.default_effect = "allow"
        APCORE_SCHEMA_ROOT=/schemas             → schema.root = "/schemas"

    Numeric strings are coerced to int/float; ``"true"``/``"false"`` become booleans.
    """
    result = copy.deepcopy(data)  # deep copy to protect shared defaults
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(_ENV_PREFIX):
            continue
        suffix = env_key[len(_ENV_PREFIX) :]
        if not suffix:
            continue
        # Convert: single _ → . (separator), double __ → literal _
        dot_path = suffix.lower().replace("__", "\x00").replace("_", ".").replace("\x00", "_")
        coerced = _coerce_env_value(env_value)
        _set_nested(result, dot_path, coerced)
    return result


def _coerce_env_value(value: str) -> Any:
    """Coerce string env value to appropriate Python type."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


class Config:
    """Configuration system with YAML loading, env overrides, and validation.

    Merge priority (highest wins): environment variables > config file > defaults.

    Backward compatible: ``Config(data={...})`` still works for in-memory
    configuration without file loading or validation.
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {}
        self._yaml_path: str | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, yaml_path: str, *, validate: bool = True) -> Config:
        """Load configuration from a YAML file with env overrides.

        Args:
            yaml_path: Path to the YAML configuration file.
            validate: If True, run full validation after loading.

        Returns:
            A new Config instance with merged data (defaults < file < env).

        Raises:
            ConfigNotFoundError: If the file does not exist.
            ConfigError: If the YAML is invalid or validation fails.
        """
        path = Path(yaml_path)
        if not path.is_file():
            raise ConfigNotFoundError(config_path=str(path))

        with open(path, encoding="utf-8") as f:
            try:
                file_data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ConfigError(message=f"Invalid YAML in {yaml_path}: {e}") from e

        if file_data is None:
            file_data = {}
        if not isinstance(file_data, dict):
            raise ConfigError(message=f"Config file must be a mapping, got {type(file_data).__name__}")

        # Merge: defaults < file < env
        merged = _deep_merge_dicts(_DEFAULTS, file_data)
        merged = _apply_env_overrides(merged)

        config = cls(data=merged)
        config._yaml_path = str(path)

        if validate:
            config.validate()

        return config

    @classmethod
    def from_defaults(cls) -> Config:
        """Create a Config from default values with env overrides applied."""
        data = _apply_env_overrides(dict(_DEFAULTS))
        return cls(data=data)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-path key."""
        with self._lock:
            return _get_nested(self._data, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by dot-path key."""
        with self._lock:
            _set_nested(self._data, key, value)

    @property
    def data(self) -> dict[str, Any]:
        """Return a deep copy of the raw config data."""
        with self._lock:
            return copy.deepcopy(self._data)

    # ------------------------------------------------------------------
    # Validation (Algorithm A12)
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validate the configuration per Algorithm A12.

        Checks required fields, type constraints, and semantic rules.
        Collects all errors before raising.

        Raises:
            ConfigError: With all validation errors in the message.
        """
        errors: list[str] = []

        # 1. Required field check
        for field in _REQUIRED_FIELDS:
            value = _get_nested(self._data, field)
            if value is None:
                errors.append(f"Missing required field: '{field}'")

        # 2. Constraint validation
        for field, (check_fn, err_msg) in _CONSTRAINTS.items():
            value = _get_nested(self._data, field)
            if value is not None and not check_fn(value):
                errors.append(f"Invalid value for '{field}': {err_msg} (got {value!r})")

        # 3. Semantic validation
        ext_root = _get_nested(self._data, "extensions.root")
        auto_discover = _get_nested(self._data, "extensions.auto_discover", False)
        if auto_discover and ext_root and not Path(str(ext_root)).exists():
            _logger.warning("extensions.auto_discover=true but extensions.root '%s' does not exist", ext_root)

        schema_strategy = _get_nested(self._data, "schema.strategy")
        schema_root = _get_nested(self._data, "schema.root")
        if schema_strategy == "yaml_only" and schema_root and not Path(str(schema_root)).exists():
            errors.append(f"schema.strategy='yaml_only' but schema.root '{schema_root}' does not exist")

        if errors:
            raise ConfigError(
                message=f"Configuration validation failed ({len(errors)} error(s)):\n"
                + "\n".join(f"  - {e}" for e in errors),
                details={"errors": errors},
            )

    # ------------------------------------------------------------------
    # Hot-reload
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-read configuration from the original YAML file.

        Only works if the Config was created via ``Config.load()``.

        Raises:
            ConfigError: If no YAML path was stored or reload fails.
        """
        with self._lock:
            yaml_path = self._yaml_path
            if yaml_path is None:
                raise ConfigError(message="Cannot reload: Config was not loaded from a YAML file")
            reloaded = Config.load(yaml_path)
            self._data = reloaded._data

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        if self._yaml_path:
            return f"Config(yaml_path={self._yaml_path!r})"
        return f"Config(data=<{len(self._data)} keys>)"
