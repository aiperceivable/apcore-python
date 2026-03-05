"""Cross-language conformance tests driven by JSON fixtures.

These tests validate behavior against shared fixtures that can be used
by any SDK implementation (Python, TypeScript, etc.) to ensure
cross-language consistency.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apcore.acl import ACL, ACLRule
from apcore.errors import (
    CallDepthExceededError,
    CallFrequencyExceededError,
    CircularCallError,
    ErrorCodeCollisionError,
    ErrorCodeRegistry,
)
from apcore.utils.call_chain import guard_call_chain
from apcore.utils.normalize import normalize_to_canonical_id
from apcore.utils.pattern import calculate_specificity, match_pattern
from apcore.version import VersionIncompatibleError, negotiate_version

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    with open(_FIXTURES / f"{name}.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Pattern matching (A09)
# ---------------------------------------------------------------------------


class TestPatternMatchingConformance:
    """Conformance tests for match_pattern()."""

    _data = _load_fixture("pattern_matching")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_pattern(self, case: dict[str, Any]) -> None:
        result = match_pattern(case["pattern"], case["value"])
        assert result == case["expected"], (
            f"match_pattern({case['pattern']!r}, {case['value']!r}) " f"returned {result}, expected {case['expected']}"
        )


# ---------------------------------------------------------------------------
# Specificity scoring (A10)
# ---------------------------------------------------------------------------


class TestSpecificityConformance:
    """Conformance tests for calculate_specificity()."""

    _data = _load_fixture("specificity")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_specificity(self, case: dict[str, Any]) -> None:
        score = calculate_specificity(case["pattern"])
        assert score == case["expected_score"], (
            f"calculate_specificity({case['pattern']!r}) " f"returned {score}, expected {case['expected_score']}"
        )


# ---------------------------------------------------------------------------
# ID normalization (A02)
# ---------------------------------------------------------------------------


class TestNormalizeIdConformance:
    """Conformance tests for normalize_to_canonical_id()."""

    _data = _load_fixture("normalize_id")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_normalize(self, case: dict[str, Any]) -> None:
        result = normalize_to_canonical_id(case["local_id"], case["language"])
        assert result == case["expected"], (
            f"normalize_to_canonical_id({case['local_id']!r}, {case['language']!r}) "
            f"returned {result!r}, expected {case['expected']!r}"
        )


# ---------------------------------------------------------------------------
# Version negotiation (A14)
# ---------------------------------------------------------------------------


class TestVersionNegotiationConformance:
    """Conformance tests for negotiate_version()."""

    _data = _load_fixture("version_negotiation")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_version(self, case: dict[str, Any]) -> None:
        if "expected_error" in case:
            error_type = case["expected_error"]
            if error_type == "VERSION_INCOMPATIBLE":
                with pytest.raises(VersionIncompatibleError):
                    negotiate_version(case["declared"], case["sdk"])
            elif error_type == "ValueError":
                with pytest.raises(ValueError):
                    negotiate_version(case["declared"], case["sdk"])
        else:
            result = negotiate_version(case["declared"], case["sdk"])
            assert result == case["expected"], (
                f"negotiate_version({case['declared']!r}, {case['sdk']!r}) "
                f"returned {result!r}, expected {case['expected']!r}"
            )


# ---------------------------------------------------------------------------
# Call chain safety (A20)
# ---------------------------------------------------------------------------

_CALL_CHAIN_ERROR_MAP: dict[str, type[Exception]] = {
    "CALL_DEPTH_EXCEEDED": CallDepthExceededError,
    "CIRCULAR_CALL": CircularCallError,
    "CALL_FREQUENCY_EXCEEDED": CallFrequencyExceededError,
}


class TestCallChainConformance:
    """Conformance tests for guard_call_chain()."""

    _data = _load_fixture("call_chain")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_call_chain(self, case: dict[str, Any]) -> None:
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
# Error code collision detection (A17)
# ---------------------------------------------------------------------------


class TestErrorCodeConformance:
    """Conformance tests for ErrorCodeRegistry."""

    _data = _load_fixture("error_codes")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_error_codes(self, case: dict[str, Any]) -> None:
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
# ACL evaluation
# ---------------------------------------------------------------------------


class TestACLEvaluationConformance:
    """Conformance tests for ACL rule evaluation."""

    _data = _load_fixture("acl_evaluation")

    @pytest.mark.parametrize(
        "case",
        _data["test_cases"],
        ids=[c["id"] for c in _data["test_cases"]],
    )
    def test_acl(self, case: dict[str, Any]) -> None:
        rules = [
            ACLRule(
                callers=r["callers"],
                targets=r["targets"],
                effect=r["effect"],
            )
            for r in case["rules"]
        ]
        acl = ACL(rules=rules, default_effect=case["default_effect"])
        result = acl.check(caller_id=case["caller"], target_id=case["target"])
        assert result == case["expected"], (
            f"ACL check(caller={case['caller']!r}, target={case['target']!r}) "
            f"returned {result}, expected {case['expected']}"
        )
