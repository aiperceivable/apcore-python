"""Tests for system.usage.module sys module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from apcore.errors import ModuleNotFoundError
from apcore.observability.usage import UsageCollector
from apcore.registry.registry import Registry
from apcore.sys_modules.usage import UsageModuleModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyModule:
    description = "dummy"

    def execute(self, inputs: dict[str, Any], context: Any) -> dict[str, Any]:
        return {}


def _make_deps(
    *,
    register_module: bool = True,
    module_id: str = "test.mod",
) -> tuple[Registry, UsageCollector, str]:
    """Create common dependencies and optionally register a dummy module."""
    registry = Registry()
    collector = UsageCollector()
    if register_module:
        registry.register(module_id, _DummyModule())
    return registry, collector, module_id


def _record_calls(
    collector: UsageCollector,
    module_id: str,
    *,
    caller_id: str = "caller-a",
    count: int = 1,
    latency_ms: float = 10.0,
    success: bool = True,
    timestamp: str | None = None,
) -> None:
    """Record usage calls in the collector."""
    for _ in range(count):
        collector.record(
            module_id=module_id,
            caller_id=caller_id,
            latency_ms=latency_ms,
            success=success,
            timestamp=timestamp,
        )


# ---------------------------------------------------------------------------
# Tests: UsageModuleModule
# ---------------------------------------------------------------------------


class TestUsageModuleSuccess:
    def test_usage_module_success(self) -> None:
        """Query an existing module; verify output contains expected fields."""
        registry, collector, module_id = _make_deps()
        _record_calls(collector, module_id, count=5, latency_ms=20.0)
        _record_calls(collector, module_id, count=2, latency_ms=30.0, success=False)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        assert result["module_id"] == module_id
        assert "period" in result
        assert result["call_count"] == 7
        assert result["error_count"] == 2
        assert "avg_latency_ms" in result
        assert "p99_latency_ms" in result
        assert "trend" in result


class TestUsageModuleNotFound:
    def test_usage_module_not_found(self) -> None:
        """Query a non-existent module_id; verify MODULE_NOT_FOUND error."""
        registry, collector, _ = _make_deps(register_module=False)
        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        with pytest.raises(ModuleNotFoundError):
            mod.execute({"module_id": "nonexistent.mod"}, None)


class TestUsageModuleDefaultPeriod:
    def test_usage_module_default_period(self) -> None:
        """Call with only module_id; verify default period='24h'."""
        registry, collector, module_id = _make_deps()
        _record_calls(collector, module_id, count=1)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        assert result["period"] == "24h"


class TestUsageModuleCallersArray:
    def test_usage_module_callers_array(self) -> None:
        """Record calls from multiple callers; verify callers array."""
        registry, collector, module_id = _make_deps()
        _record_calls(collector, module_id, caller_id="caller-a", count=3)
        _record_calls(collector, module_id, caller_id="caller-b", count=2)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        callers = result["callers"]
        assert len(callers) == 2
        caller_ids = {c["caller_id"] for c in callers}
        assert caller_ids == {"caller-a", "caller-b"}


class TestUsageModuleCallerFields:
    def test_usage_module_caller_fields(self) -> None:
        """Each caller entry contains expected fields."""
        registry, collector, module_id = _make_deps()
        _record_calls(collector, module_id, caller_id="caller-x", count=3, latency_ms=15.0)
        _record_calls(collector, module_id, caller_id="caller-x", count=1, latency_ms=25.0, success=False)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        caller = result["callers"][0]
        assert caller["caller_id"] == "caller-x"
        assert caller["call_count"] == 4
        assert caller["error_count"] == 1
        assert "avg_latency_ms" in caller


class TestUsageModuleHourlyDistribution:
    def test_usage_module_hourly_distribution(self) -> None:
        """Verify hourly_distribution contains 24 entries with expected fields."""
        registry, collector, module_id = _make_deps()
        _record_calls(collector, module_id, count=1)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        hourly = result["hourly_distribution"]
        assert len(hourly) == 24
        for entry in hourly:
            assert "hour" in entry
            assert "call_count" in entry
            assert "error_count" in entry


class TestUsageModuleHourlyDistributionCounts:
    def test_usage_module_hourly_distribution_counts(self) -> None:
        """Record calls at specific hours; verify correct bucket counts."""
        registry, collector, module_id = _make_deps()
        now = datetime.now(timezone.utc)
        # Use a timestamp 1 hour ago to ensure it is in the past
        target = now - timedelta(hours=1)
        ts = target.replace(minute=15, second=0, microsecond=0).isoformat()
        _record_calls(collector, module_id, count=3, timestamp=ts)
        _record_calls(collector, module_id, count=1, timestamp=ts, success=False)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        hourly = result["hourly_distribution"]
        hour_key = target.replace(minute=15).strftime("%Y-%m-%dT%H")
        matching = [h for h in hourly if h["hour"] == hour_key]
        assert len(matching) == 1
        assert matching[0]["call_count"] == 4
        assert matching[0]["error_count"] == 1


class TestUsageModuleP99Latency:
    def test_usage_module_p99_latency(self) -> None:
        """Record known latencies; verify p99 is approximately the 99th percentile."""
        registry, collector, module_id = _make_deps()
        # Record 100 calls: 99 at 10ms, 1 at 100ms
        for i in range(99):
            collector.record(module_id, "caller-a", 10.0, True)
        collector.record(module_id, "caller-a", 100.0, True)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        # p99 should be >= 100.0 (the 99th percentile value)
        assert result["p99_latency_ms"] >= 100.0


class TestUsageModuleAvgLatency:
    def test_usage_module_avg_latency(self) -> None:
        """Record known latencies; verify avg is the arithmetic mean."""
        registry, collector, module_id = _make_deps()
        _record_calls(collector, module_id, count=3, latency_ms=10.0)
        _record_calls(collector, module_id, count=1, latency_ms=30.0)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        # Mean of [10, 10, 10, 30] = 15.0
        assert result["avg_latency_ms"] == pytest.approx(15.0)


class TestUsageModuleTrend:
    def test_usage_module_trend(self) -> None:
        """Verify trend calculation matches expected value."""
        registry, collector, module_id = _make_deps()
        now = datetime.now(timezone.utc)

        # Record calls in the previous 24h period (24-48h ago) for comparison
        prev_ts = (now - timedelta(hours=30)).isoformat()
        _record_calls(collector, module_id, count=5, timestamp=prev_ts)

        # Record more calls in the current period (within last 24h)
        current_ts = (now - timedelta(hours=1)).isoformat()
        _record_calls(collector, module_id, count=10, timestamp=current_ts)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        # 10 vs 5 => ratio=2.0 > 1.2 => "rising"
        assert result["trend"] == "rising"


class TestUsageModulePeriod1h:
    def test_usage_module_period_1h(self) -> None:
        """Specify period='1h'; verify only last hour's data is returned."""
        registry, collector, module_id = _make_deps()
        now = datetime.now(timezone.utc)

        # Record call 2 hours ago (outside 1h window)
        old_ts = (now - timedelta(hours=2)).isoformat()
        _record_calls(collector, module_id, count=5, timestamp=old_ts)

        # Record call within last hour
        recent_ts = (now - timedelta(minutes=10)).isoformat()
        _record_calls(collector, module_id, count=3, timestamp=recent_ts)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id, "period": "1h"}, None)

        assert result["period"] == "1h"
        assert result["call_count"] == 3


class TestUsageModulePeriod7d:
    def test_usage_module_period_7d(self) -> None:
        """Specify period='7d'; verify full 7-day data is returned."""
        registry, collector, module_id = _make_deps()
        now = datetime.now(timezone.utc)

        # Record calls spread across 7 days
        for day in range(7):
            ts = (now - timedelta(days=day, hours=1)).isoformat()
            _record_calls(collector, module_id, count=2, timestamp=ts)

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id, "period": "7d"}, None)

        assert result["period"] == "7d"
        assert result["call_count"] == 14


class TestUsageModuleNoUsageData:
    def test_usage_module_no_usage_data(self) -> None:
        """Query a registered module with no calls; verify zero counts."""
        registry, collector, module_id = _make_deps()

        mod = UsageModuleModule(registry=registry, usage_collector=collector)
        result = mod.execute({"module_id": module_id}, None)

        assert result["call_count"] == 0
        assert result["error_count"] == 0
        assert result["avg_latency_ms"] == 0.0
        assert result["p99_latency_ms"] == 0.0
        assert result["callers"] == []
