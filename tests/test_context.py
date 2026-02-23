"""Tests for Context serialization (to_dict / from_dict)."""

from __future__ import annotations

from apcore.context import Context, Identity


class TestContextToDict:
    def test_round_trip_with_identity(self) -> None:
        """Create Context with Identity, serialize via to_dict(), deserialize via from_dict(), verify all fields."""
        identity = Identity(
            id="user-42",
            type="admin",
            roles=("superuser", "editor"),
            attrs={"org": "acme", "tier": "premium"},
        )
        original = Context(
            trace_id="trace-abc",
            caller_id="caller-1",
            call_chain=["mod.a", "mod.b"],
            executor="my-executor",
            identity=identity,
            redacted_inputs={"password": "***"},
            data={"transient_key": "transient_value"},
        )

        serialized = original.to_dict()
        restored = Context.from_dict(serialized)

        assert restored.trace_id == original.trace_id
        assert restored.caller_id == original.caller_id
        assert restored.call_chain == original.call_chain
        assert restored.identity is not None
        assert restored.identity.id == identity.id
        assert restored.identity.type == identity.type
        assert restored.identity.roles == identity.roles
        assert restored.identity.attrs == identity.attrs
        assert restored.redacted_inputs == original.redacted_inputs

    def test_round_trip_without_identity(self) -> None:
        """Round-trip Context with identity=None."""
        original = Context(
            trace_id="trace-xyz",
            caller_id=None,
            call_chain=[],
            identity=None,
            redacted_inputs=None,
        )

        serialized = original.to_dict()
        restored = Context.from_dict(serialized)

        assert restored.trace_id == "trace-xyz"
        assert restored.caller_id is None
        assert restored.call_chain == []
        assert restored.identity is None
        assert restored.redacted_inputs is None

    def test_executor_excluded_from_to_dict(self) -> None:
        """Verify executor is NOT present in to_dict() output."""
        ctx = Context(
            trace_id="trace-1",
            executor="should-not-appear",
            data={"key": "included"},
        )

        serialized = ctx.to_dict()

        assert "executor" not in serialized
        assert serialized["data"] == {"key": "included"}

    def test_data_public_keys_included_in_to_dict(self) -> None:
        """Verify only public data keys (not starting with '_') are serialized."""
        ctx = Context(
            trace_id="trace-1",
            data={"public_key": "visible", "_internal": "hidden"},
        )

        serialized = ctx.to_dict()

        assert serialized["data"] == {"public_key": "visible"}
        assert "_internal" not in serialized.get("data", {})

    def test_data_empty_when_no_public_keys(self) -> None:
        """Verify data is empty dict when all keys are internal."""
        ctx = Context(
            trace_id="trace-1",
            data={"_secret": "hidden"},
        )

        serialized = ctx.to_dict()

        assert serialized["data"] == {}

    def test_data_empty_when_empty(self) -> None:
        """Verify data is empty dict when data dict is empty."""
        ctx = Context(trace_id="trace-1", data={})

        serialized = ctx.to_dict()

        assert serialized["data"] == {}

    def test_executor_reinjected_via_from_dict(self) -> None:
        """Verify executor can be re-injected via from_dict()."""
        ctx = Context(trace_id="trace-2", executor="original-exec")

        serialized = ctx.to_dict()
        new_executor = {"name": "new-executor"}
        restored = Context.from_dict(serialized, executor=new_executor)

        assert restored.executor is new_executor

    def test_from_dict_defaults_executor_to_none(self) -> None:
        """from_dict() without executor argument defaults to None."""
        serialized = {"trace_id": "t1", "caller_id": None, "call_chain": [], "identity": None, "redacted_inputs": None}
        restored = Context.from_dict(serialized)
        assert restored.executor is None

    def test_to_dict_copies_call_chain(self) -> None:
        """to_dict() returns a copy of call_chain, not the original list."""
        ctx = Context(trace_id="t1", call_chain=["a", "b"])
        serialized = ctx.to_dict()
        serialized["call_chain"].append("mutated")
        assert ctx.call_chain == ["a", "b"]

    def test_to_dict_copies_identity_roles_and_attrs(self) -> None:
        """to_dict() returns copies of identity roles and attrs."""
        identity = Identity(id="u1", roles=("r1",), attrs={"k": "v"})
        ctx = Context(trace_id="t1", identity=identity)
        serialized = ctx.to_dict()
        serialized["identity"]["roles"].append("mutated")
        serialized["identity"]["attrs"]["mutated"] = True
        assert identity.roles == ("r1",)
        assert identity.attrs == {"k": "v"}
