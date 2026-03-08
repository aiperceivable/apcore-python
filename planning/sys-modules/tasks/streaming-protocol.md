# Task: Streaming Protocol Formalization — PROTOCOL_SPEC New Section (PRD F17)

## Goal

Formalize the existing streaming protocol implementation by documenting it as a new section in PROTOCOL_SPEC. This covers the `stream()` method signature, deep merge accumulation, output validation timing, fallback behavior, and depth limit. Documentation-only task; existing streaming tests already pass.

## Files Involved

- `docs/PROTOCOL_SPEC.md` -- New section documenting the streaming protocol
- `src/apcore/executor.py` (lines 789-930) -- Reference implementation to document (read-only)

## Steps

### 1. Analyze existing implementation

Read `src/apcore/executor.py` lines 789-930 to understand the current streaming protocol:

- `stream()` method signature and parameters
- Deep merge accumulation algorithm
- Output validation timing (when validation occurs relative to streaming)
- Fallback behavior when streaming is not supported
- Depth limit (32) for nested merge operations
- Error handling during streaming

### 2. Draft PROTOCOL_SPEC section

Add a new section to `docs/PROTOCOL_SPEC.md` covering:

- **Streaming Overview**: Purpose and use cases for module output streaming
- **Method Signature**: `stream(module_id, input, ...)` parameters and return type (async iterator)
- **Deep Merge Accumulation**: How partial outputs are accumulated into a final result via deep merge. Document the algorithm: dict merges recursively, lists append, scalars overwrite
- **Depth Limit**: Maximum nesting depth of 32 for merge operations; behavior when exceeded
- **Output Validation Timing**: Validation occurs on the accumulated final output, not on individual chunks. Document why (partial outputs may not satisfy the full schema)
- **Fallback Behavior**: When a module does not support streaming, the executor falls back to a single-chunk response wrapping the normal `call()` result
- **Error Handling**: How errors during streaming are propagated; partial results handling
- **Examples**: Illustrative examples of streaming a module that yields partial JSON objects

### 3. Verify consistency

- Verify the documented protocol matches the implementation in `executor.py`
- Verify existing streaming tests still pass (no code changes, but confirm test suite is green)
- Verify no contradictions with other PROTOCOL_SPEC sections

## Acceptance Criteria

- [ ] New PROTOCOL_SPEC section documents the streaming protocol comprehensively
- [ ] `stream()` method signature documented with all parameters
- [ ] Deep merge accumulation algorithm documented (dict merge, list append, scalar overwrite)
- [ ] Depth limit of 32 documented with behavior when exceeded
- [ ] Output validation timing documented (validation on final accumulated output)
- [ ] Fallback behavior documented (non-streaming modules get single-chunk wrapper)
- [ ] Error handling during streaming documented
- [ ] Documentation matches existing implementation in `executor.py` lines 789-930
- [ ] No contradictions with other PROTOCOL_SPEC sections
- [ ] Existing streaming tests continue to pass

## Dependencies

None -- documentation-only task. Existing streaming implementation and tests are already in place.

## Estimated Time

3 hours
