"""Tests for W3C Trace Context support (TraceParent, TraceContext)."""

from __future__ import annotations

import re
import uuid

import pytest

from apcore.context import Context
from apcore.trace_context import TraceContext, TraceParent

_TRACEPARENT_FORMAT = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


class TestTraceContextInject:
    """TraceContext.inject() produces valid traceparent headers."""

    def test_inject_produces_valid_traceparent_format(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        assert "traceparent" in headers
        assert _TRACEPARENT_FORMAT.match(headers["traceparent"])

    def test_inject_uses_context_trace_id(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        parts = headers["traceparent"].split("-")
        expected_hex = ctx.trace_id.replace("-", "")
        assert parts[1] == expected_hex

    def test_inject_version_is_00(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        assert headers["traceparent"].startswith("00-")

    def test_inject_trace_flags_is_01(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        assert headers["traceparent"].endswith("-01")

    def test_inject_uses_span_id_from_tracing_stack(self):
        ctx = Context.create()
        # Simulate a tracing span on the stack
        from apcore.observability.tracing import Span

        span = Span(trace_id=ctx.trace_id, name="test", start_time=0.0, span_id="abcdef0123456789")
        ctx.data["_apcore.mw.tracing.spans"] = [span]

        headers = TraceContext.inject(ctx)
        parts = headers["traceparent"].split("-")
        assert parts[2] == "abcdef0123456789"

    def test_inject_generates_parent_id_when_no_spans(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        parts = headers["traceparent"].split("-")
        parent_id = parts[2]
        assert len(parent_id) == 16
        assert re.match(r"^[0-9a-f]{16}$", parent_id)


class TestTraceContextExtract:
    """TraceContext.extract() parses traceparent headers."""

    def test_extract_valid_traceparent(self):
        headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        result = TraceContext.extract(headers)
        assert result is not None
        assert result.version == "00"
        assert result.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert result.parent_id == "00f067aa0ba902b7"
        assert result.trace_flags == "01"

    def test_extract_returns_none_for_missing_header(self):
        result = TraceContext.extract({})
        assert result is None

    def test_extract_returns_none_for_empty_dict(self):
        result = TraceContext.extract({"other-header": "value"})
        assert result is None

    def test_extract_returns_none_for_malformed_traceparent(self):
        result = TraceContext.extract({"traceparent": "invalid-format"})
        assert result is None

    def test_extract_returns_none_for_short_trace_id(self):
        result = TraceContext.extract({"traceparent": "00-abc-00f067aa0ba902b7-01"})
        assert result is None

    def test_extract_normalizes_uppercase_to_lowercase(self):
        # The regex requires lowercase; raw uppercase should still parse
        # because extract normalizes to lowercase
        headers = {"traceparent": "00-4BF92F3577B34DA6A3CE929D0E0E4736-00F067AA0BA902B7-01"}
        result = TraceContext.extract(headers)
        assert result is not None
        assert result.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_extract_returns_none_for_all_zero_trace_id(self):
        headers = {"traceparent": "00-00000000000000000000000000000000-00f067aa0ba902b7-01"}
        result = TraceContext.extract(headers)
        assert result is None

    def test_extract_returns_none_for_all_zero_parent_id(self):
        headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01"}
        result = TraceContext.extract(headers)
        assert result is None

    def test_extract_returns_none_for_version_ff(self):
        headers = {"traceparent": "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        result = TraceContext.extract(headers)
        assert result is None

    def test_extract_with_unsampled_flags(self):
        headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"}
        result = TraceContext.extract(headers)
        assert result is not None
        assert result.trace_flags == "00"


class TestTraceContextFromTraceparent:
    """TraceContext.from_traceparent() strict parsing."""

    def test_from_traceparent_valid(self):
        tp = TraceContext.from_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        assert tp.version == "00"
        assert tp.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert tp.parent_id == "00f067aa0ba902b7"
        assert tp.trace_flags == "01"

    def test_from_traceparent_raises_on_invalid(self):
        with pytest.raises(ValueError, match="Malformed traceparent"):
            TraceContext.from_traceparent("not-a-valid-traceparent")

    def test_from_traceparent_raises_on_empty(self):
        with pytest.raises(ValueError, match="Malformed traceparent"):
            TraceContext.from_traceparent("")

    def test_from_traceparent_raises_on_missing_parts(self):
        with pytest.raises(ValueError, match="Malformed traceparent"):
            TraceContext.from_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736")

    def test_from_traceparent_raises_on_all_zero_trace_id(self):
        with pytest.raises(ValueError, match="all-zero trace_id or parent_id"):
            TraceContext.from_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01")

    def test_from_traceparent_raises_on_all_zero_parent_id(self):
        with pytest.raises(ValueError, match="all-zero trace_id or parent_id"):
            TraceContext.from_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01")

    def test_from_traceparent_raises_on_version_ff(self):
        with pytest.raises(ValueError, match="version ff is not allowed"):
            TraceContext.from_traceparent("ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")


class TestTraceParentDataclass:
    """TraceParent is frozen and immutable."""

    def test_trace_parent_frozen(self):
        tp = TraceParent(version="00", trace_id="a" * 32, parent_id="b" * 16, trace_flags="01")
        with pytest.raises(AttributeError):
            tp.version = "01"  # type: ignore[misc]

    def test_trace_parent_equality(self):
        tp1 = TraceParent(version="00", trace_id="a" * 32, parent_id="b" * 16, trace_flags="01")
        tp2 = TraceParent(version="00", trace_id="a" * 32, parent_id="b" * 16, trace_flags="01")
        assert tp1 == tp2


class TestRoundTrip:
    """inject() -> extract() round-trip preserves trace_id."""

    def test_inject_then_extract_preserves_trace_id(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        parsed = TraceContext.extract(headers)

        assert parsed is not None
        expected_hex = ctx.trace_id.replace("-", "")
        assert parsed.trace_id == expected_hex

    def test_inject_then_extract_preserves_parent_id(self):
        ctx = Context.create()
        headers = TraceContext.inject(ctx)
        parsed = TraceContext.extract(headers)

        assert parsed is not None
        # parent_id in the round-trip should match what was injected
        parts = headers["traceparent"].split("-")
        assert parsed.parent_id == parts[2]


class TestContextCreateWithTraceParent:
    """Context.create(trace_parent=...) uses the trace_parent's trace_id."""

    def test_context_create_with_trace_parent_uses_trace_id(self):
        tp = TraceParent(
            version="00",
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            parent_id="00f067aa0ba902b7",
            trace_flags="01",
        )
        ctx = Context.create(trace_parent=tp)
        # trace_id should be the 32 hex reformatted as UUID (8-4-4-4-12)
        assert ctx.trace_id == "4bf92f35-77b3-4da6-a3ce-929d0e0e4736"

    def test_context_create_with_trace_parent_produces_valid_uuid(self):
        tp = TraceParent(
            version="00",
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            parent_id="00f067aa0ba902b7",
            trace_flags="01",
        )
        ctx = Context.create(trace_parent=tp)
        # Should be parseable as a UUID
        parsed = uuid.UUID(ctx.trace_id)
        assert str(parsed) == ctx.trace_id

    def test_context_create_without_trace_parent_still_works(self):
        ctx = Context.create()
        # Should produce a valid UUID v4
        parsed = uuid.UUID(ctx.trace_id)
        assert str(parsed) == ctx.trace_id

    def test_context_create_without_trace_parent_generates_unique_ids(self):
        ctx1 = Context.create()
        ctx2 = Context.create()
        assert ctx1.trace_id != ctx2.trace_id

    def test_full_round_trip_context_to_headers_and_back(self):
        """Create context -> inject headers -> extract -> create new context."""
        original = Context.create()
        headers = TraceContext.inject(original)
        parsed = TraceContext.extract(headers)
        assert parsed is not None

        restored = Context.create(trace_parent=parsed)
        assert restored.trace_id == original.trace_id
