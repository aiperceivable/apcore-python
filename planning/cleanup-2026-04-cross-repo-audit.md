# Cleanup 2026-04 — Cross-Repo Audit

> Date: 2026-04-09
> Scope: Verifies the cross-repo claims in `cleanup-2026-04.md` (lines 262-313)
>        and `cleanup-2026-04-final-summary.md` (lines 95-105) against the
>        actual current state of `apcore`, `apcore-typescript`, and `apcore-rust`.
> Method: Direct file reads (not agent paraphrase) of `PROTOCOL_SPEC.md` and
>         the relevant TS/Rust source files. Two prior-round agent claims were
>         found to be wrong and are corrected here.

## Why This File Exists

`cleanup-2026-04.md` performed a cross-repo scan that the Python team itself
rated ~70% directionally accurate / ~30% wrong on specific claims (see
`cleanup-2026-04-final-summary.md` lines 76-91). This audit re-verifies the
specific cross-repo statements before any TS/Rust cleanup work begins, so the
next round does not inherit prior-round confabulation.

## Corrections to Prior-Round Documents

Two statements in the existing cleanup-2026-04 files are demonstrably wrong
when checked against current code:

1. `cleanup-2026-04.md:311` says **"ACL singular condition aliases — not
   present in TS or Rust"**. → **Wrong for TS.** `apcore-typescript/src/acl.ts`
   lines 402-407 still register `identity_type`, `role`, `call_depth` as
   handler aliases. Rust is correct (`apcore-rust/src/acl_handlers.rs:152-154`
   plurals only).

2. `cleanup-2026-04-final-summary.md:97-105` analysis of Rust correctly
   identifies the typed-Config win, but the surrounding narrative implies
   "Rust ACL only has one check method". → **Wrong.**
   `apcore-rust/src/acl.rs:208` (sync `check`) and `:465` (async `async_check`)
   are ~95% duplicate, including a re-implemented `matches_rule_async` at
   line 518 that bypasses `match_patterns` — the same bug Python Task #3 fixed.

## Spec Ground-Truth (PROTOCOL_SPEC.md v1.6.0-draft, 2026-04-08)

Re-verified by direct read. Use this table to short-circuit any future
"the spec says X" claim.

| Concern | Spec section | Ground truth |
|---|---|---|
| Annotation field count | §4.4 (lines 750-813) | **12 fields** standardized: readonly, destructive, idempotent, requires_approval, open_world, streaming, cacheable, cache_ttl, cache_key_fields, paginated, pagination_style, extra |
| Annotation merge | §4.13 (line 1518) | **MUST field-level merge** YAML over code; spec does NOT mandate that SDKs implement YAML overlays at all — only that *if implemented*, merge must be field-level |
| Module ID via directory path | §5.2 (lines 162-184) | Applies to **file-scan path only**, not programmatic registration |
| Decorator auto-ID | §5.11.6 (lines 2530-2543) | **`{module_path}.{name}`** then normalize per §2.7. Explicitly defined |
| ACL condition keys | §6.1 (lines 3399-3400) | **Plural only**: `identity_types`, `roles`, `max_call_depth` |
| Built-in approval handlers | §7.6 (lines 3787-3789) | **Spec mandates** `AlwaysDenyHandler`, `AutoApproveHandler`, `CallbackApprovalHandler`. Not over-abstraction |
| Error format | §8.1 + §8.2 + §8.4 | Wire format `{code, message, details}`. **No class hierarchy mandated.** `CONFIG_ENV_MAP_CONFLICT` is in §8.2 |
| Metrics | §10.3 (lines 5854-5865) | **3 metrics specified** (`apcore_module_calls_total`, `apcore_module_duration_seconds`, `apcore_module_errors_total`), level **SHOULD** |
| Usage tracking | §10.4 (lines 5874-5883) | **`bucket_duration: 1h` + in-memory + per-module specified**, level SHOULD |
| OTLP / OpenTelemetry | §10.1 + impl table line 6611 | **SHOULD**, not MUST |
| Extension points | §11.3 (lines 6053-6128) | 5 extension points defined; level SHOULD |
| File scan config | §3.4/§3.6 (lines 532, 561) | `max_depth=8`, `follow_symlinks=false` are **defaults**, not constants |
| `export_schema(strict=...)` | §4.16 (line 1649) | Defined |
| `export_schema(profile=...)` | searched §4.17 | **NOT in spec** — SDK extension. Not a violation but flag if doing strict-spec compliance |
| canonical_id length | §2.7 (line 183, 210) | **192** (raised from 128 in v1.6.0-draft) |
| Config namespace + legacy modes | §9 (lines 4538, 4755-4773) | **Both formally specified**; auto-detect via `apcore:` top-level key |

## Cross-Repo State Matrix

Status legend: ✅ aligned/clean · ❌ has the issue · ⚠️ partial/conditional · N/A doesn't apply · — not investigated this round

| # | Concern | python | typescript | rust |
|---|---|---|---|---|
| **ACL** ||||
| 1 | Singular condition aliases (`identity_type`/`role`/`call_depth`) | ✅ deleted in commit `2c204fb` | ✅ deleted 2026-04-09 (Item A) | ✅ `src/acl_handlers.rs:152-154` plurals only |
| 2 | sync/async check duplication | ✅ unified in `2c204fb` | N/A all-Promise | ✅ unified 2026-04-09 (Item D) via `finalize_*` helpers |
| 3 | `matches_rule_async` re-implements pattern matching | ✅ now calls `_match_patterns` | — | ✅ AUDIT WAS WRONG — both already used `match_patterns`. Real fix: extracted `check_conditions_async` (Item D) |
| **Executor** ||||
| 4 | call/call_async/stream error-recovery triplication | ✅ `_recover_from_call_error` (`8d2f5e5`) | ✅ `executor.ts:301-304` shared | ✅ `executor.rs:436-470` shared |
| 5 | `_async_cache` dead code | ✅ deleted | ✅ absent | ✅ absent |
| 6 | Dead approval helpers | ✅ moved into `BuiltinApprovalGate` | ✅ already separated | ✅ absent |
| 7 | `_convert_validation_errors` double definition | ✅ deleted | ✅ absent | ✅ absent |
| **Errors** ||||
| 8 | 40+ class explosion | ⚠️ 42 classes — DEFERRED (P0.2) | ❌ 42 classes, same pattern | ✅ single `ModuleError` + 43-variant `ErrorCode` enum |
| 9 | Property wrappers unpacking `details` dict | ⚠️ present | ❌ present | ✅ absent (enum) |
| 10 | Unused error classes (`FeatureNotImplementedError`, `DependencyNotFoundError`) | ⚠️ still 2 | ❌ same 2 unused, exported in `index.ts` | ✅ all variants referenced |
| 11 | `ConfigEnvMapConflict` error code | ✅ in spec §8.2 | ✅ same | ✅ same |
| 12 | Over-engineered immutable `ErrorCodes` container | ⚠️ Python has setattr trap | ✅ simple `Object.freeze` | ✅ enum |
| **Registry** ||||
| 13 | `_discover_default` god method (150+ lines) | ✅ decomposed (Task #4) | ✅ `registry.ts:259-269` already 11-line orchestrator + 7 helpers | ✅ `discover()` 18 lines |
| 14 | `_DictSchemaAdapter` backwards-compat shim | ⚠️ kept (CHANGELOG-documented) | ✅ absent | ✅ absent |
| **Schema** ||||
| 15 | §4.13 field-level annotation merge wired into registry | ✅ fixed in Task #8 (commit `9c0fde9`) | ✅ `src/registry/metadata.ts:70-100` correctly calls `mergeAnnotations`/`mergeExamples`, `getDefinition` reads merged result | ❌ structural gap: no `merge_*` functions exist; `Discoverer` trait accepts pre-built `DiscoveredModule { descriptor }` so YAML overlay path simply doesn't exist |
| 16 | Schema-to-type god methods | ⚠️ KEPT (natural shape) | ✅ `loader.ts` all functions <25 LOC | ✅ `loader.rs` 30 LOC (serde) |
| 17 | Two tree walkers in `strict.ts` | ⚠️ KEPT (public API) | ✅ single walker | ✅ absent |
| 18 | `_TYPE_MAP` duplicated | ⚠️ KEPT (different domains) | ✅ no duplication | N/A |
| **Context** ||||
| 19 | `to_dict`/`from_dict` + `serialize`/`deserialize` dual API with format drift | ✅ unified (Task #6) | ⚠️ `serialize`/`deserialize` + `toJSON`/`fromJSON` exist as **intentional aliases**, output identical, no drift | ⚠️ `Context::serialize()` method + serde `Serialize` trait both exposed (mild redundancy) |
| 20 | `context_key.rs` + `context_keys.rs` two-file split | ⚠️ KEPT (cross-lang convergence) | ⚠️ same split | ⚠️ same split |
| **Builtin Steps** ||||
| 21 | `object.__setattr__` cargo-cult on `name` | ✅ deleted (Task #7) | ✅ absent | ✅ absent (no `unsafe`/`transmute` in `builtin_steps.rs`) |
| 22 | 5 strategy builders should be data-driven | ⚠️ KEPT (3-way convergence) | ⚠️ same pattern `builtin-steps.ts:600-693` | ⚠️ same pattern `builtin_steps.rs:663-727` |
| 23 | `BuiltinMiddlewareBefore` two parallel paths | ✅ unified (Round 2) | ✅ single implementation | — |
| **Config** ||||
| 24 | A12 / A12-NS dual load+validate+env-override paths | ⚠️ DEFERRED (P0.4) | ⚠️ `config.ts` is single 924-line `Config` class supporting both modes — better than Python's two-class split, but still dict-based | ✅ typed `pub struct Config { executor, observability, user_namespaces }` + `ConfigMode` enum + v0.17.x upgrade guard |
| 25 | Multi-version Pydantic fallback chain | ✅ deleted (`6587510`) | N/A TypeBox | N/A serde |
| **Annotation / Decorator** ||||
| 26 | `_CANONICAL_FIELDS` count vs spec | ✅ 12 fields | ✅ 12 fields in `schema/annotations.ts` | ✅ 13 fields (incl. extra) in `module.rs:98-116` |
| 27 | Decorator auto-ID matches spec §5.11.6 `{module_path}.{name}` | ✅ `_make_auto_id` compliant | ❓ `decorator.ts:63-70` `makeAutoId` uses `name.toLowerCase()` — **needs verification: does it actually concatenate `function.module_path`?** | N/A no proc-macro yet |
| **Approval** ||||
| 28 | Three trivial handler subclasses | ✅ spec-mandated (§7.6) — keep | ✅ same | ✅ same |
| **Observability** (spec §10 is SHOULD) ||||
| 29 | OTLP exporter | ⚠️ 91 LOC | ⚠️ 253 LOC `tracing.ts:78` | ⚠️ 125 LOC stub `exporters.rs:76` |
| 30 | Prometheus-style metrics | ✅ spec-aligned | ✅ 214 LOC `metrics.ts` | ✅ 317 LOC `metrics.rs` |
| 31 | Hourly bucketing usage tracker | ✅ spec-aligned | ✅ 294 LOC `usage.ts` | ✅ 349 LOC `usage.rs` (max 168 buckets = 7 days) |
| 32 | `error_history` ring buffer | ⚠️ 98 LOC (impl choice) | ⚠️ 120 LOC | ⚠️ 214 LOC |

## Action Items by Priority

### P0 — Concrete fixes, low risk, do in next sitting

| ID | Repo | File:line | Action | Reference | Status |
|---|---|---|---|---|---|
| **A** | apcore-typescript | `src/acl.ts:402-407` | Delete `'identity_type'`, `'role'`, `'call_depth'` handler registrations. | Mirrors Python commit `2c204fb` (Task #3); spec §6.1 | **DONE 2026-04-09**. 1699 tests pass. Singular aliases removed; spec-citation comment added |
| **B** | apcore-typescript | `src/decorator.ts:75-110` `module()` factory | **Escalated to P2 (design decision required)**. See item J below | spec §5.11.6 | INVESTIGATED 2026-04-09 — defer |

### P1 — Concrete refactors, moderate effort, do in this round

| ID | Repo | File:line | Action | Reference | Status |
|---|---|---|---|---|---|
| **C** | apcore-rust | `src/acl.rs` | **Audit claim was wrong.** Both `matches_rule` (line 329) and `matches_rule_async` (line 518) already call `Self::match_patterns()`. The actual duplication was that `matches_rule_async` inlined the conditions HashMap extraction that sync routed through `check_conditions()`. Fixed as part of Item D below by adding `check_conditions_async` helper | spec §6.3 algorithm | **DONE 2026-04-09** as part of Item D. Audit subagent's "re-implements pattern matching" claim corrected here |
| **D** | apcore-rust | `src/acl.rs:208, 465` | Consolidated sync `check` and async `async_check`. Approach (2) chosen: extracted three private helpers — `finalize_no_rules`, `finalize_rule_match`, `finalize_default_effect` — that build the audit entry, emit it, and return the bool. Both `check` and `async_check` are now thin loops over the rules calling those helpers. Also added `check_conditions_async` so `matches_rule_async` no longer inlines conditions extraction | Mirrors Python Task #3 commit `2c204fb` (`_finalize_check` helper) | **DONE 2026-04-09**. All Rust tests pass; clippy clean; src/acl.rs 572 → 596 LOC (+24, same expected refactor cost as Python). The two check methods cannot drift on audit fields, reason strings, or default-effect mapping anymore |

### P2 — Decisions required before any code changes

| ID | Repo | Question | Why it's gated |
|---|---|---|---|
| **E** | apcore-rust | Should Rust SDK support YAML annotation overlays at all? | Spec §4.13 only mandates field-level merge **if implemented**; does not require YAML overlay support. Adding it requires new file scanner, schema loader, and changes to the `Discoverer` trait. This is a feature, not a cleanup |
| **F** | apcore-rust | Drop `Context::serialize()` method in favor of serde trait only? | Need to check whether downstream consumers call `.serialize()` directly or rely on `serde_json::to_string`. Trivial to check, blocks any change |
| **G** | apcore-typescript | Is `config.ts` worth migrating to a typed Config like Rust? | TS already has a single class supporting both modes (better than Python's two-class state). Marginal value vs Rust-style typed struct migration. Defer until a concrete pain point appears |
| **J** | apcore-typescript | How should `module()` factory generate auto-IDs to comply with spec §5.11.6 `{module_path}.{name}`? | **Investigated 2026-04-09**: `decorator.ts:89` currently calls `makeAutoId('anonymous')` when `id` is omitted — every module without an explicit `id` collides on the literal string `"anonymous"`. JavaScript lacks runtime `__module__`/`__qualname__` reflection, so the Python approach (`func.__module__ + "." + func.__qualname__`) does not transfer directly. Three viable strategies: (a) **throw** when `id` is missing — safest, breaks zero existing valid usage; (b) use `options.execute.name` as fallback (works only for non-arrow named functions); (c) require callers to pass `import.meta.url` and derive a path from it. Recommendation: **(a) — throw on missing `id`**, with a clear error message pointing at spec §5.11.6. Needs maintainer sign-off because it is a breaking change for any caller relying on the silent `"anonymous"` default |

### P3 — Multi-repo design rounds (do not start without spec/design doc)

| ID | Scope | Plan |
|---|---|---|
| **H** | python + typescript errors collapse | Both have 42-class hierarchies. Rust's single `ModuleError` + `ErrorCode` enum is the target. Needs a design doc that addresses: (a) how to preserve typed `instanceof`/`isinstance` checks downstream code relies on, (b) error catalog as a frozen dict, (c) migration path with deprecation warnings. Three-repo PR in lockstep |
| **I** | apcore-python config typed migration | Python's P0.4 DEFERRED item. Reference: `apcore-rust/src/config.rs:152-200`. Estimated 500-800 LOC, breaks ~10 test files, requires Pydantic v2 model design. Owner: a future round with a written design doc first |

## Verification Snippets (for re-checking later)

When re-validating any item above, prefer these direct reads over agent paraphrase:

```bash
# Spec ground truth (always check the line, not summaries)
sed -n '750,820p'   apcore/PROTOCOL_SPEC.md  # §4.4 annotation fields
sed -n '1510,1525p' apcore/PROTOCOL_SPEC.md  # §4.13 merge rule
sed -n '2530,2545p' apcore/PROTOCOL_SPEC.md  # §5.11.6 decorator auto-ID
sed -n '3395,3410p' apcore/PROTOCOL_SPEC.md  # §6.1 ACL plural conditions
sed -n '3780,3795p' apcore/PROTOCOL_SPEC.md  # §7.6 approval handlers
sed -n '5850,5890p' apcore/PROTOCOL_SPEC.md  # §10.3-10.4 metrics + usage
sed -n '6050,6135p' apcore/PROTOCOL_SPEC.md  # §11.3 extension points

# Item A: TS ACL singular aliases
grep -n "registerCondition" apcore-typescript/src/acl.ts

# Item B: TS decorator auto-ID
sed -n '50,90p' apcore-typescript/src/decorator.ts

# Items C, D: Rust ACL duplication
sed -n '200,260p' apcore-rust/src/acl.rs
sed -n '460,540p' apcore-rust/src/acl.rs

# Item 15: TS schema §4.13 wiring (already correct, do not "fix")
sed -n '60,105p' apcore-typescript/src/registry/metadata.ts
```

## Rules for Future Cross-Repo Audits

Carrying forward `cleanup-2026-04-spec-pr-decision.md`'s lessons, plus what
this round added:

1. **Read primary sources before forming claims.** Spec line numbers > agent
   summaries. Source file:line > "the design says".
2. **Cross-language symmetry is not assumed; it is verified per-item.**
   Both `cleanup-2026-04.md:311` (TS aliases) and `final-summary.md:97-105`
   (Rust ACL singleton) made unverified symmetry claims that turned out
   wrong.
3. **A claim that "the other SDK already fixed this" is itself a claim that
   needs verification before it influences a fix recommendation.** This
   round, the TS `metadata.ts` §4.13 wiring claim was *correct* but the
   first-round agent that checked it reported it as a bug; only direct file
   read at lines 70-100 settled it.
4. **Spec compliance level matters.** Several `cleanup-2026-04.md` items
   treated SHOULD-level features (Prometheus metrics, hourly usage buckets,
   OTLP) as "scope creep" when they are spec-defined SHOULDs. Always check
   the implementation requirements table around spec line 6611 before
   labeling a feature as out-of-spec.
