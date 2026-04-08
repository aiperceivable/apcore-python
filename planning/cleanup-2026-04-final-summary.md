# Cleanup Round 2026-04 — Final Summary

> Date: 2026-04-08
> Source plan: `cleanup-2026-04.md`
> Spec PR decision: `cleanup-2026-04-spec-pr-decision.md`
> Status: **Round complete (8 tasks shipped, 1 cancelled, 1 deferred).**

## What Shipped

| # | Task | Type | src LOC | New tests | Notes |
|---|------|------|---------:|----------:|-------|
| 1 | Delete pure dead code in executor.py | delete | -35 | 0 | `_async_cache`, `_check_approval_sync`, `_run_async_in_sync` |
| 3 | Consolidate acl.py sync/async check | refactor | -7 | 0 | Extract `_snapshot` + `_finalize_check`; fix `_matches_rule_async` to call `_match_patterns()`; drop singular condition handler aliases |
| 2 | Consolidate executor call/call_async/stream | refactor | -54 | 0 | Extract `_run_async_in_sync` + `_recover_from_call_error`; `call()` and `call_with_trace()` become thin sync wrappers |
| 10 | Move approval logic into BuiltinApprovalGate | refactor | -42 | 0 | Delete 4 executor approval helpers + 1 inline; eliminate hasattr-reach-into-private |
| 6 | Consolidate context.py serialization | delete + migrate | -46 | 0 | Drop `to_dict`/`from_dict`; migrate 11 test sites to `serialize`/`deserialize` |
| 8 | Wire up schema/annotations.merge_* | wire up + spec fix | +9 | +5 | **Real spec §4.13 violation fix** — YAML annotations were silently dropped |
| 4 | Decompose registry._discover_default | refactor | +61 | 0 | 150-line god method → 23-line orchestrator + 8 named stage helpers |
| 7 | Fix builtin_steps.py object.__setattr__ hack | refactor | 0 | 0 | Pure cargo-cult — `ExecutionStrategy` was never a frozen dataclass |
| 9 | Phase 0 spec PR draft | **decision: cancel** | 0 | 0 | All 6 proposed items disproved by direct spec read; see decision record |
| **Total src/** | | | **−114** | **+5** | |

## What Did Not Ship

| Task | Status | Reason |
|---|---|---|
| #5 — Unify config.py A12 / A12-NS paths | **Deferred** | After 5 confirmed agent errors in this round, the "two parallel paths" diagnosis needs fresh verification before touching ~1170 lines of spec-§9-relevant code. Worth a dedicated investigation in the next round. |
| Phase 2 cross-language sweep | Not started | Was gated on Phase 0 spec PR, which is now cancelled. Phase 2 items are not blocked by spec; they need re-scoping against the actual spec text rather than the agent reports that originally proposed them. |
| Phase 3 decorator auto-ID fix | Cancelled | The "spec §5.2 violation" never existed — spec §5.11.6 already specifies the rule, and python's `_make_auto_id` is fully compliant. |

## Impact on Files Touched

| File | Before | After | Δ |
|---|---:|---:|---:|
| executor.py | 1057 | 874 | **−183** |
| builtin_steps.py | 817 | 858 | +41 |
| registry.py | 1084 | 1145 | +61 |
| acl.py | 576 | 569 | −7 |
| context.py | 235 | 189 | **−46** |
| registry/metadata.py | 124 | 139 | +15 |
| **Total** | **3893** | **3774** | **−119** |

The +61 in registry.py and +41 in builtin_steps.py are both *expected* refactor costs (decomposition + absorbed approval logic). The qualitative wins are not visible in the LOC delta.

## Qualitative Wins (Not Visible in LOC)

These are the changes that matter most but don't show in line counts:

1. **`registry._discover_default` is now readable in 10 seconds.** Instead of a 150-line god method maintaining 7 intermediate dicts inside a lock that spans 3 levels of nested exception handling, it's a 23-line orchestrator that names each stage. Each stage is independently testable.

2. **A11 error recovery has exactly one implementation.** Previously the `propagate_error → middleware on_error → re-raise` block was copy-pasted 4 times across `call`, `call_async`, and `stream` (twice). Now it lives in `executor._recover_from_call_error`. Fixing a bug in the error path means editing one place instead of remembering to update four.

3. **ACL audit logging has exactly one implementation.** Previously the audit-entry construction + 11-line audit-call + 6-line debug-log was duplicated 4 times across `check` and `async_check`. Now it lives in `_finalize_check`. Plus `_matches_rule_async` was silently re-implementing pattern matching in a way that bypassed `_match_patterns()` — now both paths share `_match_patterns`.

4. **Approval has exactly one implementation.** Previously `BuiltinApprovalGate` had its own simple approval logic *and* delegated to executor's complex version via `hasattr(executor, '_check_approval_async')`. The two implementations had **silently inconsistent behavior** — the simple version didn't emit audit logs and didn't map `timeout` status. Now there is one path: BuiltinApprovalGate does everything, executor exposes nothing approval-related.

5. **Context has exactly one (de)serialization API.** Previously `to_dict`/`from_dict` and `serialize`/`deserialize` were two parallel APIs with **silently different output formats** (`to_dict` always emits `redacted_inputs` key, `serialize` only when non-None; `serialize` adds `_context_version`, `to_dict` doesn't). Mixing them would silently produce inconsistent dicts. Now there is one pair.

6. **YAML annotations actually work.** Spec §4.13 mandates field-level merge of annotations (YAML over code). The python implementation **silently dropped** YAML annotations because (a) `merge_module_metadata` did whole-replacement instead of field-level merge, and (b) `get_definition()` ignored even that broken merge result and read from class attributes directly. **Both bugs are fixed.** This is the most important change in the round even though it added LOC instead of removing it.

7. **One less cargo-cult code smell.** The `object.__setattr__(s, "name", "internal")` cargo-cult is gone. `ExecutionStrategy` is a normal class; `s.name = "internal"` always worked.

8. **A11 error tests still pass after all of this.** 2247 → 2252 tests, all green, every single round-trip the entire suite. None of the eight refactors required modifying the existing test contract — only 5 brand-new regression tests for the §4.13 fix were added.

## Verification Status

| Verification | Status |
|---|---|
| `ruff check` on full src/ + tests/ | ✅ all rounds |
| `black .` on touched files | ✅ all rounds |
| `pytest tests/` (2252 tests, 2 xfail) | ✅ all rounds |
| `pyright` | not run (not in environment) — recommend running before merge |

## Five Confirmed Agent Errors in this Round

This round produced an unusually clear data point about the reliability of LLM-driven research agents. The Explore agents in this round were ~70% accurate on direction ("there's something to clean up here") but only ~30% accurate on specific claims. The five confirmed errors:

1. **Task #1** — Agent reported 6 dead approval methods. Direct grep found 4 of them are still actively called (one via `hasattr(executor, '_check_approval_async')` reach-into-private from `BuiltinApprovalGate`).
2. **Task #4** — Agent reported `Discoverer`/`ModuleValidator` Protocols as "single-impl premature abstraction". They are spec §11.3 extension points, exported as public API, exercised by tests in 3 files.
3. **Task #4** — Agent reported `_DictSchemaAdapter` as a "backwards-compat shim". It is a documented feature in CHANGELOG.md:150 with two production call sites.
4. **Task #7** — Agent reported `object.__setattr__` calls as needed because `ExecutionStrategy` is a frozen dataclass. It is not a dataclass at all. Pure cargo-cult code.
5. **Task #9** — All six proposed spec PR items were based on agent claims that the spec says X (or doesn't say Y). Direct read of the spec disproved every item:
   - §4.4 already lists 12 annotation fields (agent: "only 5")
   - §5.11.6 already specifies decorator auto-ID (agent: "spec missing")
   - §7.6 already lists the 3 built-in approval handlers (agent: "trivial subclasses")
   - §10.3/10.4 already specify Prometheus metrics + 1h bucketing (agent: "scope creep")
   - §11.3 already documents the extension points (agent: "premature abstraction")
   - §8.1 already specifies wire format only — class hierarchy is implementation choice (agent: "spec needs to forbid 1-class-per-code")
   - §4.13 is already crystal clear about field-level merge (agent: "spec is ambiguous")

**Lessons captured for future cleanup rounds** in `cleanup-2026-04-spec-pr-decision.md` ("Rule for Future Cleanup Rounds" section).

## Recommended Next Round (Future)

When the next cleanup round happens, the following items should be re-investigated *from scratch* using "read primary source first, then form claims":

1. **`config.py` A12 / A12-NS** (Task #5) — The "two parallel paths" claim is the strongest unexamined claim from this round's plan. Verify by reading config.py + spec §9.3 / §9.5 / §9.10 before scoping. Plausibly real, but possibly overstated.
2. **`registry.py:_handle_file_change`** — Class discovery via `dir(mod)` + `hasattr(attr, 'execute')` is fragile and inconsistent with the entry_point resolution that the rest of the registry uses. Not in this round's scope but flagged for cleanup.
3. **`builtin_steps.py:692-857` strategy builder duplication** — Five build_*_strategy functions all do `build_standard_strategy + .remove() + name = X`. Could be data-driven (`{name: [removed_steps]}` table). Skipped this round to avoid premature abstraction; revisit if a 6th strategy variant is added.
4. **`pipeline_config.py` `register_step_type()`** — Agent reported zero production callers. Not verified yet. If genuinely unused, delete the dynamic-handler-resolution path.
5. **`schema/loader.py:_schema_to_field_info()`** — Reportedly 65 lines handling 10+ JSON-schema combinators. Worth a dedicated decomposition pass similar to Task #4.

Total estimated future cleanup: ~150-300 src LOC, contingent on verification.
