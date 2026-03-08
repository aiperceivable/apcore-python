"""Thread-safe error history with ring-buffer eviction and deduplication."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from apcore.errors import ModuleError


@dataclass
class ErrorEntry:
    """A single error history entry."""

    module_id: str
    code: str
    message: str
    ai_guidance: str | None
    timestamp: str
    count: int
    first_occurred: str
    last_occurred: str


class ErrorHistory:
    """Thread-safe ring buffer storing recent error details per module.

    Supports deduplication by (code, message) within each module,
    per-module eviction, and global total eviction.
    """

    def __init__(
        self,
        max_entries_per_module: int = 50,
        max_total_entries: int = 1000,
    ) -> None:
        self._max_entries_per_module = max_entries_per_module
        self._max_total_entries = max_total_entries
        self._lock = threading.Lock()
        self._entries: dict[str, deque[ErrorEntry]] = {}

    def record(self, module_id: str, error: ModuleError) -> None:
        """Record an error for a module, deduplicating by (code, message)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            module_entries = self._entries.setdefault(module_id, deque())
            existing = self._find_entry(module_entries, error.code, error.message)
            if existing is not None:
                existing.count += 1
                existing.last_occurred = now
                return
            entry = ErrorEntry(
                module_id=module_id,
                code=error.code,
                message=error.message,
                ai_guidance=error.ai_guidance,
                timestamp=now,
                count=1,
                first_occurred=now,
                last_occurred=now,
            )
            module_entries.append(entry)
            self._evict_module(module_entries)
            self._evict_total()

    def get(self, module_id: str, limit: int | None = None) -> list[ErrorEntry]:
        """Return entries for a module, newest first."""
        with self._lock:
            module_entries = self._entries.get(module_id, [])
            result = list(reversed(module_entries))
            if limit is not None:
                result = result[:limit]
            return result

    def get_all(self, limit: int | None = None) -> list[ErrorEntry]:
        """Return all entries across modules, newest first."""
        with self._lock:
            all_entries: list[ErrorEntry] = []
            for entries in self._entries.values():
                all_entries.extend(entries)
            all_entries.sort(key=lambda e: e.last_occurred, reverse=True)
            if limit is not None:
                all_entries = all_entries[:limit]
            return all_entries

    @staticmethod
    def _find_entry(
        entries: deque[ErrorEntry],
        code: str,
        message: str,
    ) -> ErrorEntry | None:
        """Find an existing entry by (code, message) dedup key."""
        for entry in entries:
            if entry.code == code and entry.message == message:
                return entry
        return None

    def _evict_module(self, module_entries: deque[ErrorEntry]) -> None:
        """Remove oldest entries if module exceeds per-module limit."""
        while len(module_entries) > self._max_entries_per_module:
            module_entries.popleft()

    def _evict_total(self) -> None:
        """Remove oldest entries globally if total exceeds limit."""
        total = sum(len(entries) for entries in self._entries.values())
        while total > self._max_total_entries:
            oldest_entry: ErrorEntry | None = None
            oldest_module_id: str | None = None
            for mid, entries in self._entries.items():
                if entries:
                    candidate = entries[0]
                    if oldest_entry is None or candidate.last_occurred < oldest_entry.last_occurred:
                        oldest_entry = candidate
                        oldest_module_id = mid
            if oldest_module_id is None:
                break
            self._entries[oldest_module_id].popleft()
            if not self._entries[oldest_module_id]:
                del self._entries[oldest_module_id]
            total -= 1


__all__ = ["ErrorEntry", "ErrorHistory"]
