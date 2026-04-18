"""Cross-language conformance tests driven by canonical JSON fixtures.

These tests validate behavior against shared fixtures from the apcore
protocol specification repo. All SDK implementations (Python, TypeScript,
Rust) consume the same fixtures to ensure cross-language consistency.

Fixture source: apcore/conformance/fixtures/*.json (single source of truth).

Fixture discovery order:
  1. $APCORE_SPEC_REPO env var (explicit override)
  2. Sibling ../apcore/ directory (standard workspace layout & CI)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from apcore.acl import ACL, ACLRule
from apcore.config import (
    Config,
    _GLOBAL_ENV_MAP,
    _GLOBAL_ENV_MAP_CLAIMED,
    _GLOBAL_NS_REGISTRY,
    _GLOBAL_NS_REGISTRY_LOCK,
)
from apcore.context import Context, Identity
from apcore.errors import (
    CallDepthExceededError,
    CallFrequencyExceededError,
    CircularCallError,
    ErrorCodeCollisionError,
    ErrorCodeRegistry,
)
from apcore.schema.loader import SchemaLoader
from apcore.schema.validator import SchemaValidator
from apcore.utils.call_chain import guard_call_chain
from apcore.utils.normalize import normalize_to_canonical_id
from apcore.utils.pattern import calculate_specificity, match_pattern
from apcore.version import VersionIncompatibleError, negotiate_version

# ---------------------------------------------------------------------------
# Fixture discovery — find the canonical apcore protocol spec repo
# ---------------------------------------------------------------------------

_APCORE_REPO_ENV = "APCORE_SPEC_REPO"


def _find_apcore_fixtures() -> Path:
    """Locate the canonical conformance fixtures directory.

    Search order:
    1. $APCORE_SPEC_REPO environment variable
    2. Sibling directory: ../apcore/ relative to the apcore-python repo root
    """
    # 1. Environment variable override
    env_path = os.environ.get(_APCORE_REPO_ENV)
    if env_path:
        fixtures = Path(env_path) / "conformance" / "fixtures"
        if fixtures.is_dir():
            return fixtures
        pytest.fail(
            f"${_APCORE_REPO_ENV}={env_path} does not contain conformance/fixtures/. "
            f"Ensure the apcore protocol spec repo is at that path."
        )

    # 2. Sibling directory (standard workspace layout & CI checkout)
    repo_root = Path(__file__).resolve().parent.parent  # apcore-python/
    sibling = repo_root.parent / "apcore" / "conformance" / "fixtures"
    if sibling.is_dir():
        return sibling

    pytest.fail(
        "Cannot find apcore conformance fixtures.\n\n"
        "Fix one of:\n"
        f"  1. Set ${_APCORE_REPO_ENV} to the apcore spec repo path\n"
        f"  2. Clone apcore as a sibling: git clone <apcore-url> {repo_root.parent / 'apcore'}\n"
    )


FIXTURES_ROOT = _find_apcore_fixtures()
SCHEMAS_ROOT = FIXTURES_ROOT.parent.parent / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    """Load a JSON Schema file from the apcore spec repo's schemas/ directory."""
    path = SCHEMAS_ROOT / f"{name}.schema.json"
    if not path.exists():
        pytest.skip(f"Schema {name}.schema.json not found at {path}")
    with open(path) as f:
        return json.load(f)


def _load(name: str) -> dict[str, Any]:
    path = FIXTURES_ROOT / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Fixture {name}.json not found at {path}")
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Cleanup fixture — reset global registries between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_globals() -> Any:
    with _GLOBAL_NS_REGISTRY_LOCK:
        _GLOBAL_NS_REGISTRY.clear()
        _GLOBAL_ENV_MAP.clear()
        _GLOBAL_ENV_MAP_CLAIMED.clear()
    yield


# ---------------------------------------------------------------------------
# 1. Pattern Matching (A09)
# ---------------------------------------------------------------------------

_pattern_data = _load("pattern_matching")


@pytest.mark.parametrize(
    "case",
    _pattern_data["test_cases"],
    ids=[c["id"] for c in _pattern_data["test_cases"]],
)
def test_pattern_matching(case: dict[str, Any]) -> None:
    result = match_pattern(case["pattern"], case["value"])
    assert result == case["expected"], (
        f"match_pattern({case['pattern']!r}, {case['value']!r}) returned {result}, expected {case['expected']}"
    )


# ---------------------------------------------------------------------------
# 2. Specificity Scoring (A10)
# ---------------------------------------------------------------------------

_specificity_data = _load("specificity")


@pytest.mark.parametrize(
    "case",
    _specificity_data["test_cases"],
    ids=[c["id"] for c in _specificity_data["test_cases"]],
)
def test_specificity(case: dict[str, Any]) -> None:
    score = calculate_specificity(case["pattern"])
    assert score == case["expected_score"], (
        f"calculate_specificity({case['pattern']!r}) returned {score}, expected {case['expected_score']}"
    )


# ---------------------------------------------------------------------------
# 3. ID Normalization (A02)
# ---------------------------------------------------------------------------

_normalize_data = _load("normalize_id")


@pytest.mark.parametrize(
    "case",
    _normalize_data["test_cases"],
    ids=[c["id"] for c in _normalize_data["test_cases"]],
)
def test_normalize_id(case: dict[str, Any]) -> None:
    result = normalize_to_canonical_id(case["local_id"], case["language"])
    assert result == case["expected"], (
        f"normalize_to_canonical_id({case['local_id']!r}, {case['language']!r}) "
        f"returned {result!r}, expected {case['expected']!r}"
    )


# ---------------------------------------------------------------------------
# 4. Version Negotiation (A14)
# ---------------------------------------------------------------------------

_version_data = _load("version_negotiation")


@pytest.mark.parametrize(
    "case",
    _version_data["test_cases"],
    ids=[c["id"] for c in _version_data["test_cases"]],
)
def test_version_negotiation(case: dict[str, Any]) -> None:
    if "expected_error" in case:
        error_type = case["expected_error"]
        if error_type == "VERSION_INCOMPATIBLE":
            with pytest.raises(VersionIncompatibleError):
                negotiate_version(case["declared"], case["sdk"])
        else:
            # PARSE_ERROR or other — any exception is acceptable
            with pytest.raises(Exception):
                negotiate_version(case["declared"], case["sdk"])
    else:
        result = negotiate_version(case["declared"], case["sdk"])
        assert result == case["expected"], (
            f"negotiate_version({case['declared']!r}, {case['sdk']!r}) "
            f"returned {result!r}, expected {case['expected']!r}"
        )


# ---------------------------------------------------------------------------
# 5. Call Chain Safety (A20)
# ---------------------------------------------------------------------------

_CALL_CHAIN_ERROR_MAP: dict[str, type[Exception]] = {
    "CALL_DEPTH_EXCEEDED": CallDepthExceededError,
    "CIRCULAR_CALL": CircularCallError,
    "CALL_FREQUENCY_EXCEEDED": CallFrequencyExceededError,
}

_call_chain_data = _load("call_chain")


@pytest.mark.parametrize(
    "case",
    _call_chain_data["test_cases"],
    ids=[c["id"] for c in _call_chain_data["test_cases"]],
)
def test_call_chain(case: dict[str, Any]) -> None:
    kwargs: dict[str, Any] = {}
    if "max_call_depth" in case:
        kwargs["max_call_depth"] = case["max_call_depth"]
    if "max_module_repeat" in case:
        kwargs["max_module_repeat"] = case["max_module_repeat"]

    if "expected_error" in case:
        exc_class = _CALL_CHAIN_ERROR_MAP[case["expected_error"]]
        with pytest.raises(exc_class):
            guard_call_chain(case["module_id"], case["call_chain"], **kwargs)
    else:
        guard_call_chain(case["module_id"], case["call_chain"], **kwargs)


# ---------------------------------------------------------------------------
# 6. Error Code Collision (A17)
# ---------------------------------------------------------------------------

_error_code_data = _load("error_codes")


@pytest.mark.parametrize(
    "case",
    _error_code_data["test_cases"],
    ids=[c["id"] for c in _error_code_data["test_cases"]],
)
def test_error_codes(case: dict[str, Any]) -> None:
    registry = ErrorCodeRegistry()

    if case["action"] == "register":
        if "expected_error" in case:
            with pytest.raises(ErrorCodeCollisionError):
                registry.register(case["module_id"], {case["error_code"]})
        else:
            registry.register(case["module_id"], {case["error_code"]})

    elif case["action"] == "register_sequence":
        if "expected_error" in case:
            with pytest.raises(ErrorCodeCollisionError):
                for step in case["steps"]:
                    registry.register(step["module_id"], {step["error_code"]})
        else:
            for step in case["steps"]:
                registry.register(step["module_id"], {step["error_code"]})

    elif case["action"] == "register_unregister_register":
        for step in case["steps"]:
            if step["action"] == "register":
                registry.register(step["module_id"], {step["error_code"]})
            elif step["action"] == "unregister":
                registry.unregister(step["module_id"])


# ---------------------------------------------------------------------------
# 7. ACL Evaluation (§6)
# ---------------------------------------------------------------------------

_acl_data = _load("acl_evaluation")


def _build_acl_context(case: dict[str, Any]) -> Context:
    """Build a Context from fixture test case data."""
    identity_data = case.get("caller_identity")
    call_depth = case.get("call_depth", 0)

    if identity_data:
        identity = Identity(
            id=case.get("caller_id") or "unknown",
            type=identity_data.get("type", "user"),
            roles=tuple(identity_data.get("roles", [])),
        )
        ctx = Context.create(identity=identity)
    else:
        ctx = Context.create()

    # Simulate call depth by populating call_chain
    if call_depth > 0:
        ctx.call_chain.extend([f"_depth_{i}" for i in range(call_depth)])

    return ctx


@pytest.mark.parametrize(
    "case",
    _acl_data["test_cases"],
    ids=[c["id"] for c in _acl_data["test_cases"]],
)
def test_acl_evaluation(case: dict[str, Any]) -> None:
    rules = [
        ACLRule(
            callers=r["callers"],
            targets=r["targets"],
            effect=r["effect"],
            conditions=r.get("conditions"),
        )
        for r in case["rules"]
    ]
    acl = ACL(rules=rules, default_effect=case["default_effect"])

    # Build context if conditions, identity, or call_depth are present
    needs_context = (
        case.get("caller_identity") is not None
        or case.get("call_depth", 0) > 0
        or any(r.get("conditions") for r in case["rules"])
    )
    ctx = _build_acl_context(case) if needs_context else None

    result = acl.check(
        caller_id=case["caller_id"],
        target_id=case["target_id"],
        context=ctx,
    )
    assert result == case["expected"], (
        f"ACL check(caller_id={case['caller_id']!r}, target_id={case['target_id']!r}) "
        f"returned {result}, expected {case['expected']}"
    )


# ---------------------------------------------------------------------------
# 8. Config Env Mapping (A12-NS)
# ---------------------------------------------------------------------------

_config_env_data = _load("config_env")


@pytest.mark.parametrize(
    "case",
    _config_env_data["test_cases"],
    ids=[c["id"] for c in _config_env_data["test_cases"]],
)
def test_config_env(case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    from apcore.config import _apply_env_overrides, _apply_namespace_env_overrides

    # Register namespaces from fixture, applying test-case env_style override
    env_style = case.get("env_style", "auto")
    namespaces: list[str] = []
    for ns in _config_env_data["namespaces"]:
        if ns["name"] == "global" and "env_map" in ns:
            Config.env_map(ns["env_map"])
        else:
            Config.register_namespace(
                ns["name"],
                env_prefix=ns["env_prefix"],
                env_map=ns.get("env_map"),
                max_depth=ns.get("max_depth", 5),
                env_style=env_style,
            )
            namespaces.append(ns["name"])

    # Set the env var
    monkeypatch.setenv(case["env_var"], case["env_value"])

    with _GLOBAL_NS_REGISTRY_LOCK:
        regs = list(_GLOBAL_NS_REGISTRY.values())

    # Build initial data in namespace mode
    initial_data: dict[str, Any] = {"apcore": {}}
    for ns_name in namespaces:
        initial_data["apcore"][ns_name] = {}

    # Apply overrides
    updated_data = _apply_namespace_env_overrides(initial_data, regs)
    updated_data = _apply_env_overrides(updated_data)

    config = Config(data=updated_data, env_style=case.get("env_style", "auto"))
    config._mode = "namespace"

    if case["expected_path"] is None:
        val = config.get(case["env_var"])
        assert val is None
    else:
        result = config.get(case["expected_path"])
        expected = case["expected_value"]
        # Python Config coerces env values (e.g. "true" → True, "30000" → 30000).
        # Compare stringified values case-insensitively to account for this.
        if result is not None:
            result = str(result).lower()
        if expected is not None:
            expected = str(expected).lower()
        assert result == expected, f"config.get({case['expected_path']!r}) = {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# 9. Context Serialization (§5.7)
# ---------------------------------------------------------------------------

_ctx_ser_data = _load("context_serialization")


def _build_context_from_fixture(input_data: dict[str, Any]) -> Context:
    """Build a Context from fixture input data."""
    identity = None
    if input_data.get("identity") is not None:
        id_data = input_data["identity"]
        identity = Identity(
            id=id_data["id"],
            type=id_data.get("type", "user"),
            roles=tuple(id_data.get("roles", ())),
            attrs=id_data.get("attrs", {}),
        )

    ctx = Context(
        trace_id=input_data.get("trace_id", ""),
        caller_id=input_data.get("caller_id"),
        call_chain=list(input_data.get("call_chain", [])),
        executor=None,
        identity=identity,
        redacted_inputs=input_data.get("redacted_inputs"),
        data=dict(input_data.get("data", {})),
        services=None,
        cancel_token=None,
    )
    return ctx


# Filter out sub_cases-style tests (handled separately)
_ctx_ser_standard = [c for c in _ctx_ser_data["test_cases"] if "sub_cases" not in c]
_ctx_ser_subcases = [c for c in _ctx_ser_data["test_cases"] if "sub_cases" in c]


@pytest.mark.parametrize(
    "case",
    _ctx_ser_standard,
    ids=[c["id"] for c in _ctx_ser_standard],
)
def test_context_serialization(case: dict[str, Any]) -> None:
    case_id = case["id"]
    input_data = case["input"]
    expected = case["expected"]

    if case_id == "deserialization_round_trip":
        # Deserialize from a serialized dict, verify specific fields
        ctx = Context.deserialize(input_data)
        assert ctx.trace_id == expected["trace_id"]
        assert ctx.caller_id == expected["caller_id"]
        assert ctx.call_chain == expected["call_chain"]
        if expected.get("identity_id") is not None:
            assert ctx.identity is not None
            assert ctx.identity.id == expected["identity_id"]
            assert ctx.identity.type == expected["identity_type"]
        assert expected["data_contains"] in ctx.data
        return

    if case_id == "unknown_context_version_warns_but_proceeds":
        # Should warn but succeed
        ctx = Context.deserialize(input_data)
        assert expected["should_succeed"] is True
        assert ctx.trace_id == expected["trace_id"]
        return

    if case_id == "redacted_inputs_serialized":
        # Build context with redacted_inputs, verify they appear in serialization
        ctx = _build_context_from_fixture(input_data)
        result = ctx.serialize()
        assert result["trace_id"] == expected["trace_id"]
        assert result.get("redacted_inputs") == expected["redacted_inputs"]
        return

    # Standard serialize test: build context → serialize → compare with expected
    ctx = _build_context_from_fixture(input_data)
    result = ctx.serialize()

    assert result["_context_version"] == expected["_context_version"]
    assert result["trace_id"] == expected["trace_id"]
    assert result["caller_id"] == expected["caller_id"]
    assert result["call_chain"] == expected["call_chain"]
    assert result["identity"] == expected["identity"]
    assert result["data"] == expected["data"]


@pytest.mark.parametrize(
    "sub",
    _ctx_ser_subcases[0]["sub_cases"] if _ctx_ser_subcases else [],
    ids=[s["expected_type"] for s in (_ctx_ser_subcases[0]["sub_cases"] if _ctx_ser_subcases else [])],
)
def test_context_identity_types_serialize(sub: dict[str, Any]) -> None:
    """Each identity type round-trips through serialize → deserialize."""
    id_data = sub["input_identity"]
    identity = Identity(
        id=id_data["id"],
        type=id_data["type"],
        roles=tuple(id_data.get("roles", ())),
        attrs=id_data.get("attrs", {}),
    )
    ctx = Context.create(identity=identity)
    serialized = ctx.serialize()
    assert serialized["identity"]["type"] == sub["expected_type"]

    restored = Context.deserialize(serialized)
    assert restored.identity is not None
    assert restored.identity.type == sub["expected_type"]


# ---------------------------------------------------------------------------
# 10. Schema Validation (S4.15)
# ---------------------------------------------------------------------------

_schema_val_data = _load("schema_validation")

# Cases that require features the Python SDK doesn't yet implement
_SCHEMA_XFAIL_IDS: set[str] = set()


@pytest.fixture(scope="module")
def _schema_tools() -> tuple[SchemaLoader, SchemaValidator]:
    """Shared SchemaLoader and SchemaValidator for schema validation tests."""
    with _GLOBAL_NS_REGISTRY_LOCK:
        _GLOBAL_NS_REGISTRY.clear()
        _GLOBAL_ENV_MAP.clear()
        _GLOBAL_ENV_MAP_CLAIMED.clear()
    config = Config(data={})
    return SchemaLoader(config), SchemaValidator()


@pytest.mark.parametrize(
    "case",
    _schema_val_data["test_cases"],
    ids=[c["id"] for c in _schema_val_data["test_cases"]],
)
def test_schema_validation(
    case: dict[str, Any],
    _schema_tools: tuple[SchemaLoader, SchemaValidator],
) -> None:
    if case["id"] in _SCHEMA_XFAIL_IDS:
        pytest.xfail(f"Known gap: {case['id']}")

    loader, validator = _schema_tools
    schema = case["schema"]
    input_data = case["input"]

    # Empty schema with no properties — validator accepts any value (Draft 2020-12)
    if not schema.get("properties"):
        model = loader.generate_model(schema, f"Model_{case['id']}")
        result = validator.validate(input_data, model)
        assert result.valid == case.get("expected_valid", True)
        return

    model = loader.generate_model(schema, f"Model_{case['id']}")

    # Determine expected validity
    if "expected_valid" in case:
        expected_valid = case["expected_valid"]
    elif "expected_valid_strict" in case:
        # Pydantic default is coerce mode
        expected_valid = case["expected_valid_coerce"]
    else:
        expected_valid = True

    result = validator.validate(input_data, model)
    assert result.valid == expected_valid, (
        f"schema_validate({case['id']}) valid={result.valid}, expected={expected_valid}, errors={result.errors}"
    )

    # Verify error path when expected
    if not expected_valid and "expected_error_path" in case:
        error_paths = [e.path for e in result.errors]
        expected_path = "/" + case["expected_error_path"].replace(".", "/").replace("[", "/").replace("]", "")
        assert any(expected_path in p for p in error_paths), f"Expected error at {expected_path}, got {error_paths}"


# ---------------------------------------------------------------------------
# 11. Config Defaults
# ---------------------------------------------------------------------------

_config_defaults_data = _load("config_defaults")


@pytest.mark.parametrize(
    "case",
    _config_defaults_data["test_cases"],
    ids=[c["id"] for c in _config_defaults_data["test_cases"]],
)
def test_config_defaults(case: dict[str, Any]) -> None:
    config = Config.from_defaults()
    result = config.get(case["key"])
    assert result == case["expected"], f"Default for {case['key']}: got {result}, expected {case['expected']}"


# ---------------------------------------------------------------------------
# 12. Stream Aggregation (deep merge)
# ---------------------------------------------------------------------------

_stream_agg_data = _load("stream_aggregation")


@pytest.mark.parametrize(
    "case",
    _stream_agg_data["test_cases"],
    ids=[c["id"] for c in _stream_agg_data["test_cases"]],
)
def test_stream_aggregation(case: dict[str, Any]) -> None:
    from apcore.executor import _deep_merge

    chunks = case["chunks"]
    if not chunks:
        # no chunks -> null/empty
        assert case["expected"] is None
        return
    accumulated: dict[str, Any] = {}
    for chunk in chunks:
        _deep_merge(accumulated, chunk)
    assert accumulated == case["expected"]


# ---------------------------------------------------------------------------
# 13. Defaults Schema Completeness
# ---------------------------------------------------------------------------


def test_defaults_schema_completeness() -> None:
    """Verify that all defaults defined in defaults.schema.json
    are present and match the SDK's Config defaults."""
    schema = _load_schema("defaults")

    config = Config.from_defaults()

    def extract_defaults(props: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
        """Recursively extract (dot-path, default) pairs from schema properties."""
        results: list[tuple[str, Any]] = []
        for key, prop in props.items():
            dot_path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
            if "default" in prop:
                results.append((dot_path, prop["default"]))
            if prop.get("type") == "object" and "properties" in prop:
                results.extend(extract_defaults(prop["properties"], dot_path))
        return results

    defaults = extract_defaults(schema.get("properties", {}))
    assert len(defaults) > 0, "Schema should define at least one default"

    for dot_path, expected in defaults:
        actual = config.get(dot_path)
        assert actual == expected, f"Config default for '{dot_path}': got {actual!r}, schema says {expected!r}"


# ---------------------------------------------------------------------------
# 14. Sys Module Output Schema Validation
# ---------------------------------------------------------------------------


def test_sys_module_output_schemas_match_spec() -> None:
    """Verify that each sys module's output_schema matches the spec repo's schema file."""
    from apcore.sys_modules.control import (
        ReloadModuleModule,
        ToggleFeatureModule,
        UpdateConfigModule,
    )
    from apcore.sys_modules.health import HealthModuleModule, HealthSummaryModule
    from apcore.sys_modules.manifest import ManifestFullModule, ManifestModuleModule

    mapping: list[tuple[str, type]] = [
        ("sys-control-update-config", UpdateConfigModule),
        ("sys-control-reload-module", ReloadModuleModule),
        ("sys-control-toggle-feature", ToggleFeatureModule),
        ("sys-health-summary", HealthSummaryModule),
        ("sys-health-module", HealthModuleModule),
        ("sys-manifest-module", ManifestModuleModule),
        ("sys-manifest-full", ManifestFullModule),
    ]

    for schema_name, module_cls in mapping:
        spec_schema = _load_schema(schema_name)
        # Get the module's output_schema (class attribute)
        module_schema = getattr(module_cls, "output_schema", None)
        if module_schema is None:
            pytest.fail(f"{module_cls.__name__} has no output_schema")

        # Verify required keys match
        spec_required = set(spec_schema.get("required", []))
        module_required = set(module_schema.get("required", []))
        assert spec_required == module_required, (
            f"{schema_name}: required mismatch — spec={spec_required}, module={module_required}"
        )

        # Verify property keys match
        spec_props = set(spec_schema.get("properties", {}).keys())
        module_props = set(module_schema.get("properties", {}).keys())
        assert spec_props == module_props, (
            f"{schema_name}: properties mismatch — spec={spec_props}, module={module_props}"
        )


# ---------------------------------------------------------------------------
# Context.create trace_parent handling (PROTOCOL_SPEC §10.5)
# ---------------------------------------------------------------------------

from apcore.trace_context import TraceParent  # noqa: E402

_trace_parent_data = _load("context_trace_parent")


@pytest.mark.parametrize(
    "case",
    _trace_parent_data["test_cases"],
    ids=[c["id"] for c in _trace_parent_data["test_cases"]],
)
def test_context_create_trace_parent(case: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    import logging

    incoming = case["input"]["trace_parent_trace_id"]
    expected = case["expected"]

    if incoming is None:
        tp = None
    else:
        # Bypass TraceParent's own post-init guards so we can exercise
        # Context.create's defensive validation with every fixture input,
        # including those that a well-behaved TraceParent parser would
        # never emit (uppercase, wrong length, non-hex, empty).
        tp = TraceParent.__new__(TraceParent)
        object.__setattr__(tp, "version", "00")
        object.__setattr__(tp, "trace_id", incoming)
        object.__setattr__(tp, "parent_id", "0" * 15 + "1")
        object.__setattr__(tp, "trace_flags", "01")

    with caplog.at_level(logging.WARNING, logger="apcore.context"):
        ctx = Context.create(trace_parent=tp)

    # trace_id must always be a valid 32-char lowercase hex
    assert len(ctx.trace_id) == 32
    assert all(c in "0123456789abcdef" for c in ctx.trace_id)
    assert ctx.trace_id not in ("0" * 32, "f" * 32)

    if expected["regenerated"]:
        assert ctx.trace_id != incoming, f"Expected regeneration but kept {incoming!r}"
    else:
        assert ctx.trace_id == expected["trace_id"]

    warn_seen = any("Invalid trace_id format" in record.getMessage() for record in caplog.records)
    assert warn_seen == expected["warn_logged"], (
        f"warn_logged mismatch: expected {expected['warn_logged']}, got {warn_seen}"
    )
