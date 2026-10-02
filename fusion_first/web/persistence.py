"""Scan storage behind a small protocol."""

from __future__ import annotations

from typing import Protocol

from fusion_first.schemas import ScanResult


class ScanStore(Protocol):
    def put(self, scan_id: str, result: ScanResult) -> None: ...
    def get(self, scan_id: str) -> ScanResult | None: ...


class InMemoryScanStore:
    """Process-local, bounded, not durable."""

    def __init__(self, max_entries: int = 512):
        self._data: dict[str, ScanResult] = {}
        self._order: list[str] = []
        self._max = max_entries

    def put(self, scan_id: str, result: ScanResult) -> None:
        if scan_id not in self._data:
            self._order.append(scan_id)
        self._data[scan_id] = result
        while len(self._order) > self._max:
            evicted = self._order.pop(0)
            self._data.pop(evicted, None)

    def get(self, scan_id: str) -> ScanResult | None:
        return self._data.get(scan_id)
