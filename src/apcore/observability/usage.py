"""Time-windowed usage tracking with per-module and per-caller analytics."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from apcore.middleware import Middleware

__all__ = [
    "CallerUsageSummary",
    "HourlyBucket",
    "ModuleUsageDetail",
    "ModuleUsageSummary",
    "UsageCollector",
    "UsageMiddleware",
    "UsageRecord",
]


@dataclass
class UsageRecord:
    """A single usage event."""

    timestamp: str
    caller_id: str
    latency_ms: float
    success: bool


@dataclass
class CallerUsageSummary:
    """Per-caller usage breakdown within a module."""

    caller_id: str
    call_count: int
    error_count: int
    avg_latency_ms: float


@dataclass
class HourlyBucket:
    """Usage counts for a single hour."""

    hour: str
    call_count: int
    error_count: int


@dataclass
class ModuleUsageSummary:
    """Aggregated usage summary for a single module."""

    module_id: str
    call_count: int
    error_count: int
    avg_latency_ms: float
    unique_callers: int
    trend: str


@dataclass
class ModuleUsageDetail(ModuleUsageSummary):
    """Extended module usage with per-caller and hourly breakdowns."""

    callers: list[CallerUsageSummary] = field(default_factory=list)
    hourly_distribution: list[HourlyBucket] = field(default_factory=list)


def _parse_period(period: str) -> timedelta:
    """Convert a period string like '1h', '24h', '7d' to a timedelta."""
    if period.endswith("h"):
        return timedelta(hours=int(period[:-1]))
    if period.endswith("d"):
        return timedelta(days=int(period[:-1]))
    raise ValueError(f"Invalid period format: {period}")


def _bucket_key(ts: datetime) -> str:
    """Return an hourly bucket key like '2026-03-08T14'."""
    return ts.strftime("%Y-%m-%dT%H")


def _compute_trend(current_count: int, previous_count: int) -> str:
    """Determine trend by comparing current vs previous period counts."""
    if current_count == 0 and previous_count == 0:
        return "stable"
    if current_count == 0:
        return "inactive"
    if previous_count == 0:
        return "new"
    ratio = current_count / previous_count
    if ratio > 1.2:
        return "rising"
    if ratio < 0.8:
        return "declining"
    return "stable"


class UsageCollector:
    """Thread-safe in-memory usage tracker with hourly buckets and configurable retention."""

    def __init__(
        self,
        retention_hours: int = 168,
        max_records_per_bucket: int = 10000,
    ) -> None:
        self.retention_hours = retention_hours
        self._max_records_per_bucket = max_records_per_bucket
        self._lock = threading.Lock()
        # module_id -> bucket_key -> list[UsageRecord]
        self._data: dict[str, dict[str, list[UsageRecord]]] = {}

    def record(
        self,
        module_id: str,
        caller_id: str,
        latency_ms: float,
        success: bool,
        timestamp: str | None = None,
    ) -> None:
        """Record a usage event for a module."""
        if timestamp is None:
            now = datetime.now(timezone.utc)
            timestamp = now.isoformat()
        else:
            now = datetime.fromisoformat(timestamp)
        bk = _bucket_key(now)
        rec = UsageRecord(timestamp=timestamp, caller_id=caller_id, latency_ms=latency_ms, success=success)
        with self._lock:
            mod = self._data.setdefault(module_id, {})
            bucket = mod.setdefault(bk, [])
            if len(bucket) < self._max_records_per_bucket:
                bucket.append(rec)
            self._cleanup_expired(module_id)

    def get_summary(self, period: str = "24h") -> list[ModuleUsageSummary]:
        """Return aggregated usage summaries for all modules within the period."""
        delta = _parse_period(period)
        now = datetime.now(timezone.utc)
        cutoff = now - delta
        prev_cutoff = cutoff - delta
        with self._lock:
            return [self._build_summary(mid, cutoff, prev_cutoff, now) for mid in self._data]

    def get_module(self, module_id: str, period: str = "24h") -> ModuleUsageDetail:
        """Return detailed usage for a single module."""
        delta = _parse_period(period)
        now = datetime.now(timezone.utc)
        cutoff = now - delta
        prev_cutoff = cutoff - delta
        with self._lock:
            return self._build_detail(module_id, cutoff, prev_cutoff, now)

    def _collect_records(self, module_id: str, start: datetime, end: datetime) -> list[UsageRecord]:
        """Collect all records for a module between start and end. Must hold lock."""
        buckets = self._data.get(module_id, {})
        records: list[UsageRecord] = []
        for _bk, recs in buckets.items():
            for r in recs:
                ts = datetime.fromisoformat(r.timestamp)
                if start <= ts <= end:
                    records.append(r)
        return records

    def _build_summary(
        self,
        module_id: str,
        cutoff: datetime,
        prev_cutoff: datetime,
        now: datetime,
    ) -> ModuleUsageSummary:
        """Build a ModuleUsageSummary. Must hold lock."""
        current = self._collect_records(module_id, cutoff, now)
        previous = self._collect_records(module_id, prev_cutoff, cutoff)
        call_count = len(current)
        error_count = sum(1 for r in current if not r.success)
        avg_lat = (sum(r.latency_ms for r in current) / call_count) if call_count else 0.0
        callers = set(r.caller_id for r in current)
        trend = _compute_trend(call_count, len(previous))
        return ModuleUsageSummary(
            module_id=module_id,
            call_count=call_count,
            error_count=error_count,
            avg_latency_ms=avg_lat,
            unique_callers=len(callers),
            trend=trend,
        )

    def _build_detail(
        self,
        module_id: str,
        cutoff: datetime,
        prev_cutoff: datetime,
        now: datetime,
    ) -> ModuleUsageDetail:
        """Build a ModuleUsageDetail. Must hold lock."""
        summary = self._build_summary(module_id, cutoff, prev_cutoff, now)
        current = self._collect_records(module_id, cutoff, now)
        callers = self._per_caller_breakdown(current)
        hourly = self._hourly_distribution(current)
        return ModuleUsageDetail(
            module_id=summary.module_id,
            call_count=summary.call_count,
            error_count=summary.error_count,
            avg_latency_ms=summary.avg_latency_ms,
            unique_callers=summary.unique_callers,
            trend=summary.trend,
            callers=callers,
            hourly_distribution=hourly,
        )

    @staticmethod
    def _per_caller_breakdown(records: list[UsageRecord]) -> list[CallerUsageSummary]:
        """Group records by caller_id and compute per-caller stats."""
        by_caller: dict[str, list[UsageRecord]] = {}
        for r in records:
            by_caller.setdefault(r.caller_id, []).append(r)
        result: list[CallerUsageSummary] = []
        for cid, recs in sorted(by_caller.items()):
            cc = len(recs)
            ec = sum(1 for r in recs if not r.success)
            avg = sum(r.latency_ms for r in recs) / cc
            result.append(CallerUsageSummary(caller_id=cid, call_count=cc, error_count=ec, avg_latency_ms=avg))
        return result

    @staticmethod
    def _hourly_distribution(records: list[UsageRecord]) -> list[HourlyBucket]:
        """Group records by hour and return distribution."""
        by_hour: dict[str, list[UsageRecord]] = {}
        for r in records:
            ts = datetime.fromisoformat(r.timestamp)
            hk = _bucket_key(ts)
            by_hour.setdefault(hk, []).append(r)
        result: list[HourlyBucket] = []
        for hour_key in sorted(by_hour.keys()):
            recs = by_hour[hour_key]
            cc = len(recs)
            ec = sum(1 for r in recs if not r.success)
            result.append(HourlyBucket(hour=hour_key, call_count=cc, error_count=ec))
        return result

    def get_latencies(self, module_id: str, period: str = "24h") -> list[float]:
        """Return raw latency values for a module within the period.

        This is the public API for accessing latency data (e.g., for p99 computation).
        """
        delta = _parse_period(period)
        now = datetime.now(timezone.utc)
        cutoff = now - delta
        with self._lock:
            records = self._collect_records(module_id, cutoff, now)
            return [r.latency_ms for r in records]

    def _cleanup_expired(self, module_id: str) -> None:
        """Remove hourly buckets older than retention. Must hold lock."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        cutoff_key = _bucket_key(cutoff)
        buckets = self._data.get(module_id, {})
        expired = [bk for bk in buckets if bk < cutoff_key]
        for bk in expired:
            del buckets[bk]


class UsageMiddleware(Middleware):
    """Middleware that records module call usage via UsageCollector."""

    def __init__(self, collector: UsageCollector) -> None:
        self._collector = collector

    def before(self, module_id: str, inputs: dict[str, Any], context: Any) -> dict[str, Any] | None:
        """Store start time in context data."""
        context.data.setdefault("_usage_starts", []).append(time.time())
        return None

    def after(
        self,
        module_id: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
        context: Any,
    ) -> dict[str, Any] | None:
        """Record successful call usage."""
        latency_ms = self._pop_elapsed_ms(context)
        caller_id = context.caller_id or "unknown"
        self._collector.record(module_id, caller_id, latency_ms, success=True)
        return None

    def on_error(
        self,
        module_id: str,
        inputs: dict[str, Any],
        error: Exception,
        context: Any,
    ) -> dict[str, Any] | None:
        """Record failed call usage."""
        latency_ms = self._pop_elapsed_ms(context)
        caller_id = context.caller_id or "unknown"
        self._collector.record(module_id, caller_id, latency_ms, success=False)
        return None

    @staticmethod
    def _pop_elapsed_ms(context: Any) -> float:
        """Pop start time and return elapsed milliseconds."""
        starts = context.data.get("_usage_starts", [])
        if not starts:
            return 0.0
        start_time = starts.pop()
        return (time.time() - start_time) * 1000.0
