# Phase 0 Spec PR Decision Record

> Date: 2026-04-08
> Status: **No spec PR is being filed.**
> See `cleanup-2026-04.md` for the cleanup plan that originally proposed this Phase 0 PR.

## TL;DR

The Phase 0 spec PR proposed in `cleanup-2026-04.md` was based on Explore-agent reports that did not actually read the relevant `apcore/PROTOCOL_SPEC.md` sections before declaring "spec is unclear / spec is missing this". A direct read of the spec disproves all six items. **No spec change is required for the python cleanup work.** The cleanup work was always purely at the implementation level.

This document records the verification so future cleanup rounds do not repeat the mistake.

## Verification Against the Live Spec

Spec read at `/Users/tercelyi/Workspace/aipartnerup/apcore/PROTOCOL_SPEC.md` v1.6.0-draft (Last Updated 2026-04-08).

### Item 1 — "Errors §8 should require single class with code+details, not 1-class-per-code"

**Verdict: invalid.** Spec §8.1 (lines 3831-3874) defines the unified error format as `{code, message, details, ...}`. It does **not** mandate a class hierarchy. The 40-class hierarchies in `errors.py`/`errors.ts`/`errors.rs` are pure implementation choices. Implementations can collapse them to a single base class without any spec change.

If we want to discourage the 1-class-per-code anti-pattern across implementations, the right place is an **internal SDK style guide**, not a normative spec change.

### Item 2 — "Observability §10 ships OTLP/Prometheus/usage-bucketing/error-history that aren't in spec"

**Verdict: 80% invalid.**

- §10.3 Metrics (lines 5852-5864) **explicitly** specifies `apcore_module_calls_total` (counter), `apcore_module_duration_seconds` (histogram), and `apcore_module_errors_total` (counter) with labels. Python's `metrics.py` Prometheus-style implementation is **spec-compliant**.
- §10.4 Usage Tracking (lines 5867-5886) **explicitly** says: `storage: in-memory`, `bucket_duration: 1h`, per-module `call_count`, `error_count`, `latency_ms` histogram, `last_called_at`. Python's `usage.py` 165-line hourly bucketing implementation is **spec-compliant**.
- §10.1 Tracing (lines 5799-5827) references OpenTelemetry. OTLP exporter is reasonable spec-aligned territory but not strictly mandated.
- `error_history.py` (ring-buffer dedup) is **not mentioned** in §10. This is the only genuine "scope creep" item, and it is small (98 LOC) and clearly an internal utility, not a public API. Not worth a spec change.

### Item 3 — "ACL §6 should add an implementation note: sync should wrap async"

**Verdict: invalid as a spec change.** §6.3 (Rule Evaluation Algorithm) is single-pass pseudocode and does not distinguish sync from async. The ACL sync/async duplication in python and rust is purely a language implementation choice; the spec already permits a single implementation via either path. Adding a non-normative implementation note is possible but provides little value over an internal SDK style guide.

### Item 4 — "§4.4 only standardizes 5 annotation fields; spec needs to bless the extended 12"

**Verdict: invalid.** Spec §4.4 (lines 742-813) **already lists 12 canonical annotation fields**: `readonly`, `destructive`, `idempotent`, `requires_approval`, `open_world`, `streaming`, `cacheable`, `cache_ttl`, `cache_key_fields`, `paginated`, `pagination_style`, plus the open `extra` extension map. Spec §4.4.1 (lines 838-891) further specifies the normative wire format for `extra`. Python's 12-field `_CANONICAL_FIELDS` is **fully spec-compliant**. The original agent report was based on outdated knowledge of an earlier spec revision.

### Item 5 — "§5.2 should clarify canonical ID for programmatically-registered modules"

**Verdict: invalid.** Spec §5.11.6 (lines 2530-2543) **explicitly defines** the auto-ID rule for `module()` decorator/function:

> 1. Get callable's module path (e.g., "myapp.services.email")
> 2. Get callable's name (e.g., "send_email")
> 3. Combine as "{module_path}.{name}"
> 4. Normalize to Canonical ID format (§2.7)

Python's `decorator.py:_make_auto_id` (`f"{func.__module__}.{func.__qualname__}".replace("<locals>.", ".").lower()` + char normalization) is **fully spec-compliant** with §5.11.6. The agent referenced §5.2 (which is about file-based modules and presupposes a `file_path`) and missed §5.11.6 entirely.

### Item 6 — "§7 should discourage trivial approval handler subclasses"

**Verdict: invalid.** Spec §7.6 (lines 3781-3790) **explicitly lists** `AlwaysDenyHandler`, `AutoApproveHandler`, `CallbackApprovalHandler` as the built-in handlers implementations **should** provide. Python's three subclasses are spec-mandated, not over-abstraction.

### Bonus item — "Discoverer / ModuleValidator are premature abstraction"

**Verdict: invalid.** Spec §11.3 (lines 6053-6128) defines the extension points and even includes an explicit "Implementation Notes" table mapping theoretical names (`schema_loader`, `module_loader`, `acl_checker`) to the actual SDK names (`discoverer`, `module_validator`, `middleware`, `span_exporter`, `acl`). The python `Discoverer` / `ModuleValidator` Protocols implement spec §11.3 directly.

### Bonus item — "§4.13 annotation merge is ambiguous, python had a bug"

**Verdict: invalid as a spec gap.** Spec §4.13 (lines 1510-1518) is **completely unambiguous**:

> Implementations **must** merge rather than replace when loading: If YAML only defines `readonly: true`, other fields **must** retain values from code or defaults.

This is exactly field-level merge. My Task #8 fix was repairing a python bug (the implementation was doing whole-replacement instead of field-level merge, in violation of an unambiguous spec mandate). **Spec was clear; the bug was python's, not the spec's.**

## Why the Original Plan Got This Wrong

The Phase 0 PR plan was generated by Explore agents that I instructed to *find issues by comparing implementation to spec*. The agents reported "spec doesn't say X" or "spec only has Y" without actually reading the relevant spec sections. They mostly inferred what they thought the spec contained from filenames and section indices.

This is a known failure mode of LLM-driven research agents: they confabulate confidently when the source material is large (the spec is 7380 lines). The pattern was reinforced because *the same kinds of confabulation* showed up across both the python-only review and the cross-language scan, which I read as corroboration when it was actually just consistent confabulation.

I caught the same pattern during implementation of:

- **Task #1** (executor dead code): agent claimed 6 approval methods were dead; only 2 actually were.
- **Task #4** (registry decompose): agent claimed `Discoverer`/`ModuleValidator` were premature abstraction (they're public extension points exported in `__all__`) and `_DictSchemaAdapter` was a backwards-compat shim (it's a documented feature in CHANGELOG.md:150).
- **Task #7** (`object.__setattr__` hack): agent claimed it was needed because `ExecutionStrategy` is a frozen dataclass; it's not a dataclass at all. Pure cargo-cult code.
- **Task #9** (this document): all six proposed spec PR items.

**Pattern**: agent reports are ~70% accurate on direction ("there's something to clean up here") but ~30% accurate on specific claims about *why* it's wrong. Always verify the specific claim against primary sources before acting.

## What Phase 0 Should Have Been

If a spec PR were genuinely valuable here, it would be a tiny one:

1. **§10 add a sentence**: "`error_history` and explicit OTLP/Jaeger exporters are implementation extensions; the core spec defines only the metric/usage interfaces." (1-line clarification)
2. **§6 add a non-normative implementation note**: "Implementations that expose both sync and async ACL evaluation entry points SHOULD share a single algorithm — the sync entry point is typically a thin wrapper over the async one." (3 lines)

Neither of these is load-bearing. They are nice-to-have. **Filing a spec PR for them is not worth the round-trip cost** of opening the PR, getting it reviewed, and merging — especially because the implementations can be cleaned up at the python/ts/rust level without spec authorization.

**Decision: no Phase 0 spec PR will be filed as part of this cleanup round.** If a future cross-language refactor is blocked by spec ambiguity, that PR will be filed at that point with a specific failing case.

## Implications for the Original Cleanup Plan

`cleanup-2026-04.md` proposed three phases:

- **Phase 0 — Spec PR** → cancelled (this document)
- **Phase 1 — Python-only fixes** → 6 of 7 items completed (Tasks #1-#10, #6, #8, #4, #7); Task #5 (config A12/A12-NS) remains pending
- **Phase 2 — Cross-language sweep** → most items in this phase were also based on agent errors and should be re-scoped before being executed

In particular, Phase 2 items "errors hierarchy collapse" and "observability move-to-contrib" were **not blocked on Phase 0 spec changes** — they're allowed by the existing spec. They are still valid cleanups if we want them, but they should be re-scoped against the actual spec text rather than against the agent reports.

## Rule for Future Cleanup Rounds

When an Explore agent claims "spec doesn't say X" or "spec mandates Y":

1. **Always read the cited spec section.** If the agent did not cite a section, do not act on the claim.
2. **Read the surrounding 2 sections too.** Spec topics span multiple sections (e.g., §4.4 Annotations is referenced by §4.13 Conflict Rules and §5.11.6 Decorator ID).
3. **Treat agent confidence as orthogonal to agent accuracy.** An agent saying "this is clearly a spec violation" is no more reliable than an agent saying "this might be worth checking".
4. **Cleanups that touch spec-defined behavior require spec citation in the commit message.** This forces verification at commit time.
