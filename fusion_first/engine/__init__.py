"""Scan/proof orchestration built on the pure pieces (judge, stats, goldset).

`report.py` fuses the proof bars into a Safety Report Card; `before_after.py` runs the paired
before/after evaluation. Both are offline-deterministic when given a ReplayModelClient.
"""
