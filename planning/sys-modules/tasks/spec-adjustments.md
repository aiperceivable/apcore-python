# Task: Specification Adjustments — 5 Documentation Changes (PRD F16)

## Goal

Apply five specification adjustments to the protocol documentation. These are documentation-only changes that refine positioning, relax certain requirements from MUST to SHOULD/MAY, and update schema defaults. No code changes required.

## Files Involved

- `docs/PROTOCOL_SPEC.md` -- Primary specification document (sections 1.1, directory-as-ID, IDConverter, $ref, schema defaults)
- Related docs in `docs/` directory as needed

## Steps

### 1. Identify current text (verification)

Locate and record the current text for each of the five adjustments:

- **16a**: Find "universal framework" positioning in PROTOCOL_SPEC section 1.1
- **16b**: Find directory-as-ID MUST requirement
- **16c**: Find IDConverter cross-language MUST requirement
- **16d**: Find `$ref` resolution requirements
- **16e**: Find schema default `yaml_first` setting

### 2. Apply adjustments

- **16a — Positioning update**: Change "universal framework" to "AI-Perceivable standard" as primary positioning in PROTOCOL_SPEC section 1.1. Ensure all references to primary positioning use the new term.
- **16b — Directory-as-ID relaxation**: Change directory-as-ID from MUST to SHOULD. Implementations may use alternative ID derivation strategies.
- **16c — IDConverter cross-language relaxation**: Change IDConverter cross-language requirement from MUST to MAY. Cross-language ID conversion is optional.
- **16d — $ref resolution tiering**: Update `$ref` requirements to tiered levels:
  - Local `$ref` (same file): MUST support
  - Cross-file `$ref`: SHOULD support
  - `apcore://` protocol `$ref`: MAY support
- **16e — Schema default change**: Change schema default from `yaml_first` to `native_first`. Native language schema definitions take precedence over YAML-based schemas by default.

### 3. Verify no regressions

- Search for any remaining instances of "universal framework" used as primary positioning (some historical or comparative mentions may be acceptable)
- Verify MUST/SHOULD/MAY usage is consistent with RFC 2119 throughout the modified sections
- Ensure no contradictions introduced with other sections of the spec

## Acceptance Criteria

- [ ] 16a: "universal framework" replaced with "AI-Perceivable standard" as primary positioning in section 1.1
- [ ] 16b: Directory-as-ID requirement changed from MUST to SHOULD
- [ ] 16c: IDConverter cross-language requirement changed from MUST to MAY
- [ ] 16d: `$ref` requirements tiered: local MUST, cross-file SHOULD, `apcore://` MAY
- [ ] 16e: Schema default changed from `yaml_first` to `native_first`
- [ ] No instance of "universal framework" remains as primary positioning
- [ ] All MUST/SHOULD/MAY usage follows RFC 2119 conventions
- [ ] No contradictions with other specification sections

## Dependencies

None -- documentation-only changes, independent of code tasks.

## Estimated Time

2 hours
