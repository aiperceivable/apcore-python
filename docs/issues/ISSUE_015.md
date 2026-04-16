### Problem
The event system was emitting redundant legacy event aliases alongside the canonical ones defined in PROTOCOL_SPEC §9.16. For example, a module toggle emitted both `module_health_changed` and `apcore.module.toggled`. This increased event processing overhead and created confusion regarding which event name to use.

### Why
When the new canonical event naming convention was introduced in v0.15, a transition period was established during which both names were emitted. The original deadline for removing these aliases was v0.16.0, but they were kept in the codebase until v0.18.0.

### Solution
Removed all dual-emission logic in v0.18.0. The following legacy names were dropped:
- `module_health_changed` (use `apcore.module.toggled` or `apcore.health.recovered`)
- `config_changed` (use `apcore.config.updated` or `apcore.module.reloaded`)

### Verification
Updated all tests in `tests/events/` and `tests/sys_modules/` to subscribe only to canonical event names and verified that no legacy event names are being emitted via `EventEmitter`.
