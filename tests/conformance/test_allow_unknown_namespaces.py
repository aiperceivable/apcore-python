"""Drive `allow_unknown_namespaces.json` — §9.6.3 `_config.allow_unknown` (#118 D-69).

Both halves of the `strict: false` row were inert. `allow_unknown: false` is
documented as "silently ignored (not stored)" and the namespace was stored
anyway; `allow_unknown: true` is documented as "stored, accessible, **WARN
logged**" and nothing logged. Fixing one without the other leaves the row half
true, so the fixture drives both — and the legacy-mode boundary besides, so the
namespace-only scoping is a decision rather than an omission.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from apcore.config import Config
from apcore.errors import ConfigError

from .canonical_fixtures import case_ids, load_fixture

FIXTURE = load_fixture("allow_unknown_namespaces.json")
CASES: dict[str, dict[str, Any]] = {tc["id"]: tc for tc in FIXTURE["test_cases"]}

_BASE = {"version": "1.0", "project": {"name": "allow-unknown-probe"}}


def _document(spec: dict[str, Any]) -> dict[str, Any]:
    doc: dict[str, Any] = {"apcore": dict(_BASE)} if spec["mode"] == "namespace" else dict(_BASE)
    if spec["config"] is not None:
        doc["_config"] = dict(spec["config"])
    if spec["namespace"] is not None:
        doc[spec["namespace"]] = {"x": 1}
    return doc


@pytest.mark.parametrize("case_id", list(CASES))
def test_allow_unknown_namespaces(case_id: str, caplog: pytest.LogCaptureFixture) -> None:
    case = CASES[case_id]
    spec, expected = case["input"], case["expected"]
    path = Path(tempfile.mkdtemp()) / "apcore.yaml"
    path.write_text(yaml.safe_dump(_document(spec)), encoding="utf-8")

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        if expected.get("loads") is False:
            with pytest.raises(ConfigError) as excinfo:
                Config.load(str(path))
            assert excinfo.value.code == expected["error_code"]
            assert expected["error_message_contains"] in str(excinfo.value)
            return
        config = Config.load(str(path))

    if "value_readable" in expected:
        value = config.get(f"{spec['namespace']}.x")
        assert (value is not None) is expected["value_readable"], value

    messages = [r.getMessage() for r in caplog.records]
    if "warns_naming" in expected:
        hits = [m for m in messages if expected["warns_naming"] in m and "registered" in m]
        assert len(hits) == 1, messages
    if "warns_absent" in expected:
        assert not any(expected["warns_absent"] in m for m in messages), messages


def test_every_fixture_case_is_driven() -> None:
    assert set(case_ids("allow_unknown_namespaces.json")) == set(CASES)
