# Cross-Language Sync Report — 2026-04-09

> Generated after cleanup-2026-04 cross-repo audit round.
> Scope: apcore (spec) + apcore-python + apcore-typescript + apcore-rust
> Method: Full public API extraction from all 3 SDKs via parallel sub-agents,
>         then cross-comparison against each other and spec.

## Result: No regressions from cleanup-2026-04 commits

All 12 commits from the cleanup session (4 repos) were verified to introduce
**zero new cross-language inconsistencies**. The 4 areas we changed are now
**more consistent** than before:

| Area | Before | After |
|------|--------|-------|
| ACL condition aliases | py: plural only, ts: singular+plural, rust: plural only | All 3: **plural only** |
| ACL sync/async check | py: shared helpers, ts: N/A (Promise), rust: duplicated | All 3: **shared audit construction** |
| `module()` factory auto-ID | py: auto, ts: silent 'anonymous' collision, rust: no factory | py: auto, ts: **throws on missing id**, rust: no factory — all spec-compliant |
| Zombie error classes | py: 2 zero-raise classes, ts: same 2, rust: N/A (enum) | py: **deleted**, ts: **deleted**, rust: enum variants remain (correct) |

## Pre-existing divergences (not caused by this session)

These are intentional and documented. Listed here as baseline for future audits:

1. **Python `APCore.module()` is a decorator** — TS `module()` is a factory,
   Rust has no equivalent. Spec §5.11.6 allows this because the decorator
   syntax is only available in Python.

2. **Rust `Config` is typed** (`ExecutorConfig`, `ObservabilityConfig` structs)
   — Python/TS are dict-based. Spec §9 does not mandate either approach.

3. **Rust `Registry.register()` requires a pre-built `ModuleDescriptor`** —
   Python/TS auto-construct it from the module object + metadata YAML.
   Related to the YAML annotation overlay difference (see Rust README).

4. **TS exports `ToggleState` as a public class** — Python/Rust handle toggle
   state internally via sys-module.

5. **Rust `stream()` returns `Vec<Value>`** (collected) — Python/TS return
   `AsyncGenerator`/`AsyncIterator` (lazy). Rust's tokio `Stream` trait is
   not stable enough for public API; collected vec is the interim choice.

6. **Rust has no `_handle_file_change` / hot-reload path** — Python has it
   (refactored in this session to use `resolve_entry_point`), TS has `watch()`.

7. **Error class count**: Python 40 classes, TS 40 classes, Rust 1 struct +
   43 enum variants. Spec §8.1 does not mandate a class hierarchy. The
   Rust approach (single `ModuleError` + `ErrorCode` enum) is the target
   model for a future deprecation cycle (cleanup-2026-04 P0.2).

## Export count baseline

| SDK | Total exports | Error classes/variants | Other classes | Functions | Constants |
|-----|--------------|----------------------|--------------|-----------|-----------|
| Python | ~155 | 40 | ~50 | ~30 | ~15 |
| TypeScript | ~188 | 40 | ~55 | ~40 | ~20 |
| Rust | ~101 | 1 + 43 variants | ~55 | ~20 | ~10 |

## Recommended next steps

1. Finalize release-prep CHANGELOG.md edits in apcore-python and apcore-typescript
2. Run `/apcore-skills:audit` in a fresh session on clean working trees
3. The audit should specifically verify:
   - PROTOCOL_SPEC.md section references in all 3 SDKs' code comments
   - README examples match current API signatures (especially after module() change)
   - Test coverage for the new `module()` throw behavior in TS
   - Conformance test alignment across all 3 SDKs
