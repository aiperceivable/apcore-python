# apcore-python Cleanup Plan (2026-04)

> Source: full code-quality review on 2026-04-08 against apcore PROTOCOL_SPEC.md.
> Goal: shrink ~16k LOC by ~30% without dropping spec-mandated functionality.
> Method: remove duplication, dead code, premature abstraction, and out-of-spec scope creep.

---

## Executive Summary

The codebase shows organic growth without consolidation. Six "god files" account for most of the bloat:

| File | Current LOC | Target LOC | Primary issue |
|---|---:|---:|---|
| `errors.py` | 1003 | ~280 | 42 exception subclasses + property wrappers replicating `details` dict |
| `executor.py` | 1057 | ~550 | sync/async/stream code paths duplicated 3x; dead approval methods |
| `registry.py` | 1084 | ~600 | 153-line `_discover_default` god method; legacy DictSchemaAdapter shim |
| `builtin_steps.py` | 817 | ~500 (split) | `object.__setattr__` hack on frozen dataclass; config-extract pattern repeated |
| `config.py` | ~1170 | ~600 | Parallel A12 (legacy) and A12-NS (namespace) algorithms |
| `acl.py` | 576 | ~280 | `check`/`async_check` 95% duplicated; audit-logging blocks repeated 4 times |
| **Total reduction** | **~5700** | **~2810** | **~2900 LOC removed** |

Plus ~1500 LOC reduction across observability/, context*.py, schema/, approval.py.

**Estimated total cleanup: ~5000 LOC (~31% of codebase).**

---

## P0 — Structural Problems (Must Fix)

### P0.1 Sync/Async Duplication (the biggest single issue)

The codebase tries to support both sync and async APIs by writing each method twice. This is the largest source of duplication.

| Location | Evidence |
|---|---|
| `acl.py:237-302` vs `304-369` | `check()` and `async_check()` are 95% identical; only difference is `await` on `_matches_rule_async` |
| `acl.py:260-280, 327-347` | Audit logging block duplicated **4 times** verbatim |
| `acl.py:93-119` vs `121-141` | `_evaluate_conditions` / `_evaluate_conditions_async` near-duplicates |
| `acl.py:442-466` vs `468-490` | `_matches_rule_async` reimplements pattern matching instead of reusing `_match_patterns()` |
| `executor.py:311-386` / `718-764` / `766-863` | `call`/`call_async`/`stream` share ~60 lines of error-recovery boilerplate (translate abort → propagate → middleware on_error → re-raise) replicated 3x |
| `executor.py:104` vs `builtin_steps.py:63` | `_convert_validation_errors` defined twice |
| `builtin_steps.py:303-395` | `BuiltinMiddlewareBefore` has two parallel paths (manager vs list) with duplicated on_error handling |

**Fix**: Async-first. Sync entry points become 1-line wrappers: `loop.run_until_complete(self._async_impl(...))`. Estimated savings: ~600 LOC.

### P0.2 errors.py — 42 Exception Classes vs Spec's ~25 Codes

Spec §8 defines error **codes** (`code` + `message` + `details` dict). The implementation invented an OO hierarchy on top, with property wrappers that just unpack the details dict.

| Issue | Location |
|---|---|
| Property wrappers extracting from `details` dict | `errors.py:259-267, 295-304, 356-359, 422-430, 514-588` (~80 lines of boilerplate accessors) |
| Unused exception classes (zero raise sites) | `errors.py:784-810` `FeatureNotImplementedError`, `DependencyNotFoundError` |
| Over-engineered immutable `ErrorCodes` class | `errors.py:813-872` uses `__setattr__`/`__delattr__` for what should be a dict |
| `_UNSET` sentinel for one parameter default | `errors.py:61` |
| Module-load-time dynamic collision detection | `errors.py:898-905` `_collect_framework_codes` |
| Out-of-spec error code | `errors.py` `ConfigEnvMapConflictError` (CONFIG_ENV_MAP_CONFLICT not in spec §8.2) |
| 42 entries in `__all__` exports | `errors.py:15-59` |

**Fix**: One `ModuleError(code, message, details)` base + ~8-10 spec-mandated subclasses. Callers use `err.details["caller_id"]` directly. Estimated savings: ~720 LOC.

### P0.3 registry.py `_discover_default` — 153-Line God Method [COMPLETED 2026-04-08]

`registry.py:298-447` did 8 sequential things (scan, id_map, metadata, entry_point resolve, validate, dependencies, conflict-check, register), maintained 7 intermediate dicts, held a lock through the entire on_load callback loop with 3 levels of nested exception handling.

**Resolution**: Decomposed into a 23-line orchestrator + 8 named stage helpers (`_scan_params`, `_scan_roots`, `_apply_id_map_overrides`, `_load_all_metadata`, `_resolve_all_entry_points`, `_validate_all`, `_resolve_load_order`, `_filter_id_conflicts`, `_register_in_order`). Also extracted `_invoke_on_load` to flatten the rollback logic. LOC went from 1084 → 1145 (+61) — pure refactor cost; readability win is qualitative.

**Earlier scan claims that turned out to be WRONG and were not acted on**:

- ~~`registry.py:81-103` `Discoverer` and `ModuleValidator` Protocols are premature abstraction~~ — **FALSE**. These are public extension-point API exported from `apcore.__init__`, used by `extensions.py`, exercised by `tests/test_extensions.py`, `tests/registry/test_registry.py::TestCustomDiscoverer`, and locked in `tests/test_public_api.py`. They are user extension hooks, not premature abstraction. **Kept.**

- ~~`registry.py:36-61` `_DictSchemaAdapter` is a backwards-compat shim~~ — **FALSE**. It is a documented feature: CHANGELOG.md:150 says *"Dict schema support — Modules can now define input_schema/output_schema as plain JSON Schema dicts."* Called from two registration paths. **Kept.**

- ~~`registry.py:951-1015` `_handle_file_change` class discovery via `dir(mod)`~~ — Still present; flagged as a known fragility but not in this refactor's scope.

- ~~`registry.py:259-296` `_discover_custom` duplicates discovery~~ — Different semantics: custom path takes pre-instantiated modules from external systems (DB/S3), default path does file scanning + class resolution. Not duplication; not unified.

### P0.4 config.py — Parallel A12 and A12-NS Algorithms

Spec describes A12-NS as a superset of A12 (namespace mode); legacy mode is a degenerate case (namespace = `""`). The implementation has them as parallel code paths.

| Duplication | Location |
|---|---|
| Two load methods | `config.py:725-757` `_load_legacy_mode` / `_load_namespace_mode` |
| Two validate methods iterating same `_CONSTRAINTS` dict | `config.py:939-978` `validate()` vs `980-1029` `_validate_namespace_mode()` |
| Two env override paths | `config.py:227-247` `_apply_env_overrides` vs `369-432` `_apply_namespace_env_overrides` |
| Three-level helper chain for suffix→dot-path | `config.py:267-294, 319-346` `_env_suffix_to_dot_path_with_depth` / `_auto_resolve_suffix` / `_match_suffix_to_tree` |
| 5-step Pydantic v2 → v1 → dataclass → constructor fallback | `config.py:1079-1116` `_instantiate_model` (historical baggage, not spec-mandated) |

**Fix**: Treat legacy as `register_namespace("")`. One load, one validate, one env-override path. Drop multi-version Pydantic fallbacks (project requires v2). Estimated savings: ~570 LOC.

---

## P1 — Over-Design and Dead Code

### P1.1 Context Has Three Serialization Paths

`context.py` has both `to_dict()`/`serialize()` and `from_dict()`/`deserialize()`:
- `context.py:77-99` `to_dict()`
- `context.py:122-147` `serialize()` (adds version field)
- `context.py:102-120` `from_dict(executor=...)` — asymmetric, takes executor that the serialize side doesn't emit
- `context.py:150-187` `deserialize()`

**Fix**: One `to_dict`/`from_dict` pair.

### P1.2 context_key.py + context_keys.py — Two Files for One Concept

One holds the `ContextKey[T]` class, the other holds singleton constants. Inconsistent naming (`TRACING_SPANS` plural vs `LOGGING_START` singular at `context_keys.py:6-11`).

**Fix**: Merge into one file.

### P1.3 Executor Dead Code

| Location | Dead element |
|---|---|
| `executor.py:215-216` | `_async_cache`, `_async_cache_lock` declared but never assigned |
| `executor.py:507-591` | `_needs_approval`, `_build_approval_request`, `_check_approval_sync`, `_check_approval_async`, `_run_async_in_sync` — superseded by `BuiltinApprovalGate`, no longer called |
| `executor.py:663-664` | "Removed in v0.17" comment block remnants |

### P1.4 builtin_steps.py — `object.__setattr__` Hack on Frozen Dataclass

`builtin_steps.py:754, 773, 791, 816` use `object.__setattr__()` to mutate the `name` field of a frozen dataclass. This indicates the dataclass is wrong: either drop `frozen=True` or move `name` out of the dataclass.

Also `builtin_steps.py:692-817` — five strategy builder functions (`standard`, `internal`, `testing`, `performance`, `minimal`) all use `.remove()` + `object.__setattr__` patterns. Should be data-driven.

### P1.5 approval.py — Trivial Handler Subclasses

`approval.py:92-114` `AlwaysDenyHandler` and `AutoApproveHandler` are 11 lines each just to return a static result. `approval.py:116-136` `CallbackApprovalHandler` is a 21-line pass-through wrapper.

**Fix**: One `StaticApprovalHandler(decision)` plus the callback wrapper, or use functions.

### P1.6 schema/annotations.py — Unused Spec Implementation

`schema/annotations.py` defines `merge_annotations`, `merge_examples`, `merge_metadata` per spec §4.13 (YAML > code > defaults priority). **The schema loader never calls them.** This is a broken-window: spec §4.13 is *not* actually implemented despite the code stub existing.

**Fix**: Either wire it up in `schema/loader.py` or delete and document the spec gap.

### P1.7 Observability Out-of-Spec Scope Creep

Spec §10 defines logging/metrics/usage as SHOULD-level interfaces. The implementation went far beyond:

| File | Issue |
|---|---|
| `observability/tracing.py:103-194` | 91-line OTLP exporter; spec only mentions OTLP as an example |
| `observability/usage.py:104-269` | 165 lines of hourly bucketing + retention + trending; spec only requires "report which modules are in use" |
| `observability/error_history.py` | 98-line ring-buffer dedup utility; spec doesn't mention error history at all |
| `observability/metrics.py` | Full Prometheus-style API with histograms/buckets; spec doesn't mandate this |

**Fix**: Move OTLP, usage analytics, error history out of `core` into `apcore.observability.contrib` (or a separate package). Core keeps only the interfaces.

### P1.8 schema/strict.py — Two Tree Walkers

`schema/strict.py:49-72` `_strip_extensions` and `75-113` `_convert_to_strict` both walk the entire schema tree. Schemas get traversed twice. Combine into one visitor pass.

### P1.9 Pipeline Extension Points Nobody Uses

| Location | Unused extension |
|---|---|
| `pipeline_config.py` | `register_step_type()` and dynamic handler resolution — zero production callers |
| `pipeline.py:129-137` | `StrategyInfo` introspection metadata, never used at runtime |
| `pipeline.py:56-57` | `BaseStep.requires`/`provides` only validated at strategy build, not runtime-enforced |
| `pipeline.py:167-187` | `ExecutionStrategy.insert_after`/`insert_before` exists but `executor.stream()` builds strategies inline at line 859 instead of using these |

### P1.10 Schema Loader Bloat

| Location | Issue |
|---|---|
| `schema/loader.py:118-240` | `generate_model()` + 7 private helpers totaling 120 LOC |
| `schema/loader.py:140-205` | `_schema_to_field_info()` is a 65-line method handling const/enum/oneOf/anyOf/allOf/nullable/primitives/objects/arrays |
| `schema/loader.py:357-364` | `_load_and_resolve()` duplicates the model cache check already done at line 327 |
| `schema/loader.py:23-29` vs `bindings.py:43-64` | `_TYPE_MAP` duplicated between two files |
| `schema/validator.py:13-31` | Hand-maintained `_PYDANTIC_TO_CONSTRAINT` mapping (19 entries) |

---

## P2 — Spec Divergence (Needs User Confirmation)

These are deviations from the spec that may be intentional but should be acknowledged or removed:

| Location | Divergence |
|---|---|
| `decorator.py:255-306` `@module` | Auto-generates module ID from function `__qualname__`. Spec §5.2 mandates **directory-path** canonical ID. |
| `module.py:47-60` `_CANONICAL_FIELDS` | Defines 12 annotation fields; spec §4.4 only standardizes 5 (`readonly`, `destructive`, `idempotent`, `requires_approval`, `open_world`) |
| `acl.py:78-85` | Condition handlers register both singular and plural keys (`identity_type`/`identity_types`, `role`/`roles`, `call_depth`/`max_call_depth`); spec §6.1 only defines singular form |
| `errors.py` `ConfigEnvMapConflictError` | Error code `CONFIG_ENV_MAP_CONFLICT` not in spec §8.2 |
| `schema_export.py:69-96` | Export accepts `profile` and `strict` parameters not in spec §4 |
| `registry.py:299-305` | Reads `extensions.max_depth` and `extensions.follow_symlinks` from config; spec §3.4 mandates `max_depth=8` and `follow_symlinks=false` constants |

---

## Recommended Execution Order

1. **acl.py sync→async unification** — lowest-risk, biggest readability win, sets the pattern for executor.py
2. **executor.py sync/async unification + delete dead approval methods** — applies the same pattern, removes dead code in one pass
3. **errors.py shrink** — independent file, large absolute LOC win, low risk
4. **registry.py `_discover_default` decomposition** — pure refactor with strong test coverage available
5. **context.py serialization consolidation + merge context_key files** — small but cleans the public API
6. **config.py A12/A12-NS unification** — riskier; do after the easier wins to build confidence
7. **builtin_steps.py split + fix `object.__setattr__` hack** — touches public step API, do once and carefully
8. **observability move-to-contrib** — touches packaging and potentially user imports; requires CHANGELOG entry
9. **schema/annotations.py — wire up or delete** — requires user decision on whether spec §4.13 should be implemented

---

## Cross-Repo Findings (Completed 2026-04-08)

Parallel quick scans of `apcore-typescript` and `apcore-rust` were performed against the same 14 issue list. Result: **the python implementation is the worst of the three.** TS and Rust have already solved several issues that python still carries.

### Issues confirmed shared across all 3 languages → require SPEC-LEVEL fix

These cannot be cleaned up in python alone — they reflect spec ambiguity that pushed every implementation toward the same anti-pattern.

| Issue | Python | TypeScript | Rust |
|---|---|---|---|
| **Error type explosion** (1 type per code, property-wrapper accessors over `details` dict) | 42 classes / 1003 LOC | 43 classes / 908 LOC | 39 structs / 45-variant enum / 1382 LOC |
| **ACL sync + async duplication** (95% identical `check` / `async_check`) | yes | yes (justified by TS type system) | yes (NOT justified — Rust could use one async path) |
| **Observability scope creep** (OTLP exporter, Prometheus-style metrics, hourly bucketing usage tracker, error-history ring buffer all shipped in core) | ~1100 LOC | ~1180 LOC | ~3347 LOC |
| **Approval trivial handler subclasses** (AlwaysDeny, AutoApprove, Callback wrapper) | yes | yes | yes |
| **`_CANONICAL_FIELDS` defines 12+ annotation fields, spec §4.4 only standardizes 5** | yes | yes | yes (13 fields) |
| **`@module` / `module()` decorator derives ID from function/class name, not directory path** (spec §5.2 violation) | yes | yes | (gap: macro not yet implemented) |

**Spec-side actions needed (apcore repo, not apcore-python):**

1. **Errors §8** — Add normative guidance: "Implementations SHOULD use a single error type carrying `code` + `message` + `details` dict. Implementations SHOULD NOT create one error class per code." Cite the explosion as anti-pattern.
2. **Observability §10** — Demote OTLP, Prometheus metrics, usage analytics, and error-history to "MAY" or move to a separate `apcore-observability-contrib` spec. Core spec §10 should define only the **interface contracts**.
3. **ACL §6** — Add a non-normative implementation note: "If the language requires both sync and async APIs, the sync version SHOULD be a thin wrapper over the async implementation. Do not duplicate rule-matching logic."
4. **Annotations §4.4** — Either formally bless the extended 12-field set (streaming, cacheable, cache_ttl, cache_key_fields, paginated, pagination_style, extra) or require implementations to drop them.
5. **Decorator auto-ID §5.2** — Clarify: when a module is registered programmatically (via decorator) outside a directory scan, what is the canonical ID? Currently all 3 implementations cheat by using the function name, which violates the directory-as-ID principle.
6. **Approval §7** — Strategy interface guidance: "Implementations SHOULD NOT ship multiple trivial approval handler classes; provide one parameterizable handler or a factory function."

### Issues Python ONLY (TS / Rust have already done it right)

Python should **borrow the working pattern** from the sibling implementation rather than invent fresh.

| Python issue | Reference implementation | What to copy |
|---|---|---|
| `registry.py:298-447` 153-line `_discover_default` god method | `apcore-typescript/src/registry/registry.ts:259-395` | TS decomposes into 7 named private methods (`_scanRoots`, `_applyIdMapOverrides`, `_loadAllMetadata`, `_resolveAllEntryPoints`, `_validateAll`, `_resolveLoadOrder`, `_registerInOrder`). Mirror this exactly in python. |
| `config.py:725-757, 939-978, 980-1029` parallel A12 / A12-NS load + validate + env-override | `apcore-rust/src/config.rs:275-430` | Rust has a single `load()` and single `validate()` with namespace and legacy as the same path; legacy is namespace=`""`. Adopt this model. |
| `executor.py:311-386, 718-764, 766-863` `call`/`call_async`/`stream` triple duplication | TS `executor.ts:317-324` and Rust `executor.rs:436-469` both have `call_async` simply delegate to the async core | Python `call()` should be a 1-line `loop.run_until_complete(self._call_async(...))` wrapper. |
| `schema/loader.py:118-240` 120-LOC schema-to-Pydantic chain | `apcore-rust/src/schema/loader.rs:45-100` | Rust has no schema-to-type bloat — serde handles it. Python can't fully replicate (needs Pydantic), but TS keeps each combinator function under 25 LOC (`apcore-typescript/src/schema/loader.ts:200-281`). Use TS as the size budget. |
| `context.py:77-187` four serialization methods | `apcore-rust/src/context.rs:243-323` | Rust has only `serialize`/`deserialize` plus serde derive. TS has `serialize`/`deserialize` + thin `toJSON`/`fromJSON` aliases. Drop the to_dict/from_dict pair, keep serialize/deserialize. |
| `schema/annotations.py merge_*` defined but never called by loader | `apcore-typescript/src/registry/registry.ts:375` calls `mergeModuleMetadata` | TS correctly wires the merge into the metadata pipeline per spec §4.13. Either copy this wiring into python or delete the dead code. |
| `errors.py:813-872` over-engineered immutable `ErrorCodes` class | TS uses `Object.freeze({...})` (1 line) | Replace with `Final` dict or frozen dataclass. |

### Issues Python-specific (no cross-lang reference, but still bad code)

| Python issue | Notes |
|---|---|
| `executor.py:215-216` `_async_cache` declared, never used | Pure dead code — delete. |
| `executor.py:507-591` dead approval methods | Pipeline migration left these orphaned — delete. |
| `builtin_steps.py:754,773,791,816` `object.__setattr__` hack on frozen dataclass | TS/Rust have no equivalent (Rust uses honest `&mut`). Fix the dataclass design: drop `frozen=True` or move `name` out. |
| `registry.py:36-61` `_DictSchemaAdapter` backwards-compat shim | TS has no equivalent (static typing rejects); spec requires schema classes. Delete. |
| `context_key.py` + `context_keys.py` two-file split | TS has the same split (file count = 2), Rust treats it as intentional. Verdict: borderline — leave for now, defer to a style decision, **not P0**. |
| `acl.py:78-85` condition-handler key aliases (singular + plural) | Not present in TS or Rust. Delete plural variants. |
| `config.py:1079-1116` 5-step Pydantic v2/v1/dataclass/constructor fallback chain | Pure historical baggage — pyproject already requires Pydantic v2. Drop fallbacks. |

---

## Updated Execution Strategy

The cross-language scan changes the order significantly:

**Phase 0 — Spec clarifications (apcore repo)** [CANCELLED 2026-04-08]
~~Open one PR against `apcore/PROTOCOL_SPEC.md` covering items 1-6 from the "spec-level fix" table above.~~

**Verdict**: Cancelled. All 6 proposed items were based on Explore-agent claims that did not actually read the relevant spec sections. Direct verification against PROTOCOL_SPEC.md disproves every item — the spec already covers each case (annotations §4.4 has 12 fields, decorator ID §5.11.6, observability §10.3/10.4 has metrics+bucketing, approval handlers §7.6, extension points §11.3, error format §8.1, annotation merge §4.13). See `cleanup-2026-04-spec-pr-decision.md` for the full per-item verification.

**Implication for Phase 2**: items in Phase 2 (errors hierarchy collapse, observability move-to-contrib, ACL sync→async wrap) were not actually blocked on spec changes — they are permitted by the existing spec. They remain valid as cleanups but should be re-scoped against the actual spec text rather than against the agent reports.

**Phase 1 — Python-only structural fixes (apcore-python)**
These do NOT require spec changes; they are pure cleanup catching python up to TS/Rust.
1. Decompose `_discover_default` using the TS template (`registry.ts:259-395` as reference).
2. Unify `call`/`call_async`/`stream` error recovery — `call` becomes a 1-line wrapper.
3. Unify `config.py` legacy/namespace paths using the Rust model.
4. Consolidate `context.py` serialization to one pair of methods.
5. Delete dead code: `_async_cache`, dead approval methods, `_DictSchemaAdapter`, Pydantic v1 fallbacks, ACL plural-key aliases.
6. Fix `builtin_steps.py` `object.__setattr__` hack via dataclass design fix.
7. Wire up or delete `schema/annotations.merge_*`.

**Phase 2 — Cross-language sweep (after spec PR merges)**
Apply the spec-blessed cleanups to all 3 languages in lockstep:
1. Errors collapse: 39-43 types → ~10 types per language.
2. Observability move-to-contrib.
3. ACL sync→async wrapper consolidation (Rust included; TS may keep due to language constraint).
4. Approval handler factory consolidation.

**Phase 3 — Decorator auto-ID** (after spec §5.2 clarification)
All three languages currently violate spec §5.2 in the same way; the fix is gated on the spec deciding what the canonical ID is for programmatically-registered modules.

---

## Estimated Total Reduction (Updated)

| Phase | Python LOC removed | TS LOC removed | Rust LOC removed |
|---|---:|---:|---:|
| Phase 1 (python-only) | ~2200 | — | — |
| Phase 2 (cross-lang sweep) | ~2500 | ~2000 | ~3500 |
| Phase 3 (decorator) | ~150 | ~150 | (n/a, macro not yet built) |
| **Python total** | **~4850 (~30%)** | | |
