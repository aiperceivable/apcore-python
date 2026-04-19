"""Regression tests for Registry on_load failure rollback."""

from __future__ import annotations

import pytest
from apcore.registry.registry import Registry
from apcore.errors import ModuleError


class _BadModule:
    module_id = "test.rollback.bad"
    description = "bad module that fails on_load"

    def execute(self, inputs, context):
        pass

    def on_load(self):
        raise ModuleError("fail", code="LOAD_FAIL")

    def on_unload(self):
        pass


def test_register_rollback_clears_lowercase_map():
    """After on_load failure, lowercase_map must not retain the entry."""
    registry = Registry()
    with pytest.raises(Exception):
        registry.register("test.rollback.bad", _BadModule())
    # lowercase_map must not retain the entry
    assert "test.rollback.bad" not in registry._lowercase_map
