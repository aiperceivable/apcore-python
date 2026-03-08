# Task: Config Extensions for sys_modules Section (PRD F6)

## Goal

Extend the existing `Config` class to support the `sys_modules` configuration section with defaults, YAML loading, and environment variable overrides. Also add `project.source_repo` and `project.source_root` fields.

## Files Involved

- `src/apcore/config.py` -- Modify `_DEFAULTS` and optionally `_CONSTRAINTS`
- `tests/test_config.py` -- Add new test cases for sys_modules config

## Steps

### 1. Write failing tests (TDD)

Add to `tests/test_config.py`:

- **test_config_sys_modules_defaults**: Create `Config.from_defaults()`; verify all sys_modules defaults:
  - `sys_modules.enabled` = `False`
  - `sys_modules.error_history.max_entries_per_module` = `50`
  - `sys_modules.error_history.max_total_entries` = `1000`
  - `sys_modules.events.enabled` = `False`
  - `sys_modules.events.thresholds.error_rate` = `0.1`
  - `sys_modules.events.thresholds.latency_p99_ms` = `5000`
  - `sys_modules.events.subscribers` = `[]`
- **test_config_project_source_repo_default**: Verify `project.source_repo` defaults to `None`
- **test_config_project_source_root_default**: Verify `project.source_root` defaults to `""`
- **test_config_sys_modules_from_yaml**: Load a YAML file with `sys_modules.enabled: true`; verify it overrides the default
- **test_config_sys_modules_env_override**: Set `APCORE_SYS__MODULES_ENABLED=true` env var; verify `sys_modules.enabled` is `True`
- **test_config_sys_modules_nested_env_override**: Set `APCORE_SYS__MODULES_ERROR__HISTORY_MAX__ENTRIES__PER__MODULE=100`; verify override works
- **test_config_sys_modules_events_thresholds_yaml**: Load YAML with custom thresholds; verify they are read correctly
- **test_config_sys_modules_subscribers_yaml**: Load YAML with a subscriber list; verify it parses correctly
- **test_config_project_source_repo_yaml**: Load YAML with `project.source_repo: "https://github.com/org/repo"`; verify
- **test_config_project_source_root_yaml**: Load YAML with `project.source_root: "src/modules"`; verify

### 2. Modify _DEFAULTS in config.py

Add to the `_DEFAULTS` dict:

```python
"project": {
    "name": "apcore",
    "source_repo": None,
    "source_root": "",
},
"sys_modules": {
    "enabled": False,
    "error_history": {
        "max_entries_per_module": 50,
        "max_total_entries": 1000,
    },
    "events": {
        "enabled": False,
        "thresholds": {
            "error_rate": 0.1,
            "latency_p99_ms": 5000.0,
        },
        "subscribers": [],
    },
},
```

### 3. Add constraints (optional but recommended)

Add to `_CONSTRAINTS`:

- `sys_modules.error_history.max_entries_per_module`: must be positive integer
- `sys_modules.error_history.max_total_entries`: must be positive integer
- `sys_modules.events.thresholds.error_rate`: must be float in [0.0, 1.0]
- `sys_modules.events.thresholds.latency_p99_ms`: must be positive float

### 4. Verify tests pass

Run `pytest tests/test_config.py -v`.

## Acceptance Criteria

- [ ] `_DEFAULTS` includes `sys_modules` section with all specified defaults
- [ ] `_DEFAULTS` includes `project.source_repo` (None) and `project.source_root` ("")
- [ ] `Config.from_defaults()` returns correct sys_modules values
- [ ] YAML loading merges sys_modules values correctly
- [ ] Environment variable `APCORE_SYS__MODULES_ENABLED=true` overrides `sys_modules.enabled`
- [ ] Nested env overrides work for error_history and events config
- [ ] Constraints validate sys_modules numeric fields
- [ ] Tests achieve >= 90% coverage of new config paths
- [ ] All test names follow `test_<unit>_<behavior>` convention

## Dependencies

- Existing `src/apcore/config.py` Config class

## Estimated Time

2 hours
