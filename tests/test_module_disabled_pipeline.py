"""Regression test: module-disabled check must be enforced in the execution pipeline.

Issue 1: is_module_disabled() / check_module_disabled() are defined but were
never called during module execution.  TypeScript and Rust return MODULE_DISABLED
(HTTP 403) when a module is toggled off.  Python must raise ModuleDisabledError.

This test FAILS before the fix and PASSES after.
"""

from __future__ import annotations

from typing import Any

import pytest

from apcore.errors import ModuleDisabledError
from apcore.executor import Executor
from apcore.registry import Registry
from apcore.sys_modules.control import ToggleState, _default_toggle_state


class _EchoModule:
    description = "echo"
    input_schema = None
    output_schema = None

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        return {"echoed": inputs}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_global_toggle() -> Any:
    """Ensure global toggle state is clean before and after each test."""
    _default_toggle_state.clear()
    yield
    _default_toggle_state.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestModuleDisabledPipeline:
    def test_disabled_module_raises_module_disabled_error(self) -> None:
        """Calling a disabled module MUST raise ModuleDisabledError."""
        registry = Registry()
        registry.register("math.add", _EchoModule())
        executor = Executor(registry=registry)

        # Disable the module via the global toggle state
        _default_toggle_state.disable("math.add")

        with pytest.raises(ModuleDisabledError):
            executor.call("math.add", {"x": 1})

    def test_enabled_module_executes_normally(self) -> None:
        """A non-disabled module must execute normally."""
        registry = Registry()
        registry.register("math.add", _EchoModule())
        executor = Executor(registry=registry)

        result = executor.call("math.add", {"x": 1})
        assert result == {"echoed": {"x": 1}}

    def test_re_enabled_module_executes_after_toggle(self) -> None:
        """After re-enabling, the module should execute normally again."""
        registry = Registry()
        registry.register("math.add", _EchoModule())
        executor = Executor(registry=registry)

        _default_toggle_state.disable("math.add")
        with pytest.raises(ModuleDisabledError):
            executor.call("math.add", {})

        _default_toggle_state.enable("math.add")
        result = executor.call("math.add", {})
        assert result == {"echoed": {}}

    def test_disabled_check_respects_custom_toggle_state(self) -> None:
        """BuiltinModuleLookup must accept an injected ToggleState instance."""
        from apcore.builtin_steps import BuiltinModuleLookup

        registry = Registry()
        registry.register("svc.foo", _EchoModule())

        custom_state = ToggleState()
        custom_state.disable("svc.foo")

        step = BuiltinModuleLookup(registry=registry, toggle_state=custom_state)
        # Verify that the step has the injected toggle_state
        assert step._toggle_state is custom_state
