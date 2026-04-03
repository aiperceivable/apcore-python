import json
import threading
import os
from pathlib import Path
import pytest
from apcore.utils import normalize_to_canonical_id, match_pattern, calculate_specificity
from apcore.acl import ACL
from apcore.config import Config, _GLOBAL_NS_REGISTRY, _GLOBAL_NS_REGISTRY_LOCK, _GLOBAL_ENV_MAP, _GLOBAL_ENV_MAP_CLAIMED
from apcore.version import negotiate_version
from apcore.errors import ErrorCodes, ErrorCodeRegistry

# Fixtures root relative to this test file
FIXTURES_ROOT = Path(__file__).parent.parent.parent.parent / "apcore" / "conformance" / "fixtures"

def load_fixture(name):
    path = FIXTURES_ROOT / f"{name}.json"
    with open(path) as f:
        return json.load(f)

@pytest.fixture(autouse=True)
def cleanup_globals():
    """Clear global registries before each test to ensure isolation."""
    with _GLOBAL_NS_REGISTRY_LOCK:
        _GLOBAL_NS_REGISTRY.clear()
        _GLOBAL_ENV_MAP.clear()
        _GLOBAL_ENV_MAP_CLAIMED.clear()
    yield

# --- 1. ID Normalization (A02) ---
normalize_fixture = load_fixture("normalize_id")
@pytest.mark.parametrize("case", normalize_fixture["test_cases"], ids=lambda c: c["id"])
def test_normalize_id_conformance(case):
    result = normalize_to_canonical_id(case["local_id"], case["language"])
    assert result == case["expected"]

# --- 2. Pattern Matching (A09) ---
pattern_fixture = load_fixture("pattern_matching")
@pytest.mark.parametrize("case", pattern_fixture["test_cases"], ids=lambda c: c["id"])
def test_pattern_matching_conformance(case):
    result = match_pattern(case["pattern"], case["value"])
    assert result == case["expected"]

# --- 3. ACL Specificity (A10) ---
specificity_fixture = load_fixture("specificity")
@pytest.mark.parametrize("case", specificity_fixture["test_cases"], ids=lambda c: c["id"])
def test_specificity_conformance(case):
    result = calculate_specificity(case["pattern"])
    assert result == case["expected_score"]

# --- 4. ACL Evaluation ---
acl_fixture = load_fixture("acl_evaluation")
@pytest.mark.parametrize("case", acl_fixture["test_cases"], ids=lambda c: c["id"])
def test_acl_evaluation_conformance(case):
    from apcore.acl import ACLRule
    rules = []
    for rule_data in case["rules"]:
        rules.append(ACLRule(
            callers=rule_data["callers"],
            targets=rule_data["targets"],
            effect=rule_data["effect"],
            conditions=rule_data.get("conditions")
        ))
    
    acl = ACL(rules=rules, default_effect=case["default_effect"])
    
    identity_data = case.get("caller_identity")
    call_depth = case.get("call_depth", 0)
    
    from apcore.context import Context, Identity
    ctx = Context.create()
    if identity_data:
        ctx._identity = Identity(
            id=case["caller_id"] or "unknown",
            type=identity_data["type"],
            roles=tuple(identity_data.get("roles", []))
        )
    ctx._call_chain = ["fake"] * call_depth

    result = acl.check(
        caller_id=case["caller_id"],
        target_id=case["target_id"],
        context=ctx
    )
    assert result == case["expected"]

# --- 5. Config Env Mapping (A12-NS) ---
config_env_fixture = load_fixture("config_env")
@pytest.mark.parametrize("case", config_env_fixture["test_cases"], ids=lambda c: c["id"])
def test_config_env_conformance(case, monkeypatch):
    namespaces = []
    for ns in config_env_fixture["namespaces"]:
        if ns["name"] == "global" and "env_map" in ns:
            Config.env_map(ns["env_map"])
        else:
            Config.register_namespace(
                ns["name"], 
                env_prefix=ns["env_prefix"],
                env_map=ns.get("env_map"),
                max_depth=ns.get("max_depth", 5)
            )
            namespaces.append(ns["name"])
    
    # Mock environment variable
    monkeypatch.setenv(case["env_var"], case["env_value"])
    
    from apcore.config import _apply_namespace_env_overrides, _apply_env_overrides
    
    with _GLOBAL_NS_REGISTRY_LOCK:
        regs = list(_GLOBAL_NS_REGISTRY.values())
    
    # 1. Start with empty dict in namespace mode
    initial_data = {"apcore": {}}
    # Ensure nested keys exist so _apply_namespace_env_overrides can find them
    for ns_name in namespaces:
        initial_data["apcore"][ns_name] = {}
        
    # 2. Apply namespace overrides
    updated_data = _apply_namespace_env_overrides(initial_data, regs)
    
    # 3. Apply global mapping overrides
    updated_data = _apply_env_overrides(updated_data)
    
    config = Config(data=updated_data, env_style=case.get("env_style", "auto"))
    config._mode = "namespace" 
    
    if case["expected_path"] is None:
        val = config.get(case["env_var"])
        assert val is None
    else:
        result = config.get(case["expected_path"])
        # Coerce type
        if isinstance(case["expected_value"], int) and result is not None:
            result = int(result)
        elif isinstance(case["expected_value"], bool):
             if isinstance(result, str):
                result = result.lower() == "true"
        
        assert result == case["expected_value"]

# --- 6. Version Negotiation (A14) ---
version_fixture = load_fixture("version_negotiation")
@pytest.mark.parametrize("case", version_fixture["test_cases"], ids=lambda c: c["id"])
def test_version_negotiation_conformance(case):
    if "expected_error" in case:
        with pytest.raises(Exception) as excinfo:
            negotiate_version(case["declared"], case["sdk"])
        error_name = case["expected_error"]
        assert error_name in str(excinfo.type) or error_name in str(excinfo.value)
    else:
        result = negotiate_version(case["declared"], case["sdk"])
        assert result == case["expected"]

# --- 7. Error Code Collision (A17) ---
error_code_fixture = load_fixture("error_codes")
@pytest.mark.parametrize("case", error_code_fixture["test_cases"], ids=lambda c: c["id"])
def test_error_code_conformance(case):
    registry = ErrorCodeRegistry()
    
    if case["action"] == "register":
        if "expected_error" in case:
            with pytest.raises(Exception):
                registry.register(case["module_id"], {case["error_code"]})
        else:
            registry.register(case["module_id"], {case["error_code"]})
            
    elif case["action"] == "register_sequence":
        for step in case["steps"]:
            if "expected_error" in case and step == case["steps"][-1]:
                with pytest.raises(Exception):
                    registry.register(step["module_id"], {step["error_code"]})
            else:
                registry.register(step["module_id"], {step["error_code"]})
                
    elif case["action"] == "register_unregister_register":
        for step in case["steps"]:
            if step["action"] == "register":
                registry.register(step["module_id"], {step["error_code"]})
            else:
                registry.unregister(step["module_id"])
