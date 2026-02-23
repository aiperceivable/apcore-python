"""W3C Trace Context support: TraceParent parsing and TraceContext injection/extraction."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, TypeAlias

Context: TypeAlias = Any


__all__ = ["TraceParent", "TraceContext"]

_TRACEPARENT_RE = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True)
class TraceParent:
    """Parsed W3C traceparent header fields."""

    version: str  # "00"
    trace_id: str  # 32 lowercase hex chars
    parent_id: str  # 16 lowercase hex chars
    trace_flags: str  # "01" (sampled) or "00"


class TraceContext:
    """Utilities for W3C Trace Context propagation."""

    @staticmethod
    def inject(context: Context) -> dict[str, str]:
        """Build a traceparent header dict from an apcore Context.

        Converts ``context.trace_id`` (UUID with dashes) to the 32-hex
        format required by the W3C traceparent spec.  Uses the first
        span's ``span_id`` from the tracing stack if available, otherwise
        generates a random 16-hex parent id.
        """
        trace_id_hex = context.trace_id.replace("-", "")

        spans_stack = context.data.get("_tracing_spans")
        if spans_stack:
            parent_id = spans_stack[-1].span_id
        else:
            parent_id = os.urandom(8).hex()

        traceparent = f"00-{trace_id_hex}-{parent_id}-01"
        return {"traceparent": traceparent}

    @staticmethod
    def extract(headers: dict[str, str]) -> TraceParent | None:
        """Parse the ``traceparent`` header from *headers*.

        Returns ``None`` if the header is missing or malformed.
        """
        raw = headers.get("traceparent")
        if raw is None:
            return None
        match = _TRACEPARENT_RE.match(raw.strip().lower())
        if match is None:
            return None
        version = match.group(1)
        trace_id = match.group(2)
        parent_id = match.group(3)
        if version == "ff":
            return None
        if trace_id == "0" * 32 or parent_id == "0" * 16:
            return None
        return TraceParent(
            version=version,
            trace_id=trace_id,
            parent_id=parent_id,
            trace_flags=match.group(4),
        )

    @staticmethod
    def from_traceparent(traceparent: str) -> TraceParent:
        """Strictly parse a traceparent string, raising on invalid format.

        Raises:
            ValueError: If *traceparent* does not match the expected
                ``00-{32hex}-{16hex}-{2hex}`` format.
        """
        match = _TRACEPARENT_RE.match(traceparent.strip().lower())
        if match is None:
            raise ValueError(
                f"Malformed traceparent: {traceparent[:100]!r}. " "Expected format: 00-<32 hex>-<16 hex>-<2 hex>"
            )
        version = match.group(1)
        trace_id = match.group(2)
        parent_id = match.group(3)
        if version == "ff":
            raise ValueError("Invalid traceparent: version ff is not allowed")
        if trace_id == "0" * 32 or parent_id == "0" * 16:
            raise ValueError("Invalid traceparent: all-zero trace_id or parent_id")
        return TraceParent(
            version=version,
            trace_id=trace_id,
            parent_id=parent_id,
            trace_flags=match.group(4),
        )
