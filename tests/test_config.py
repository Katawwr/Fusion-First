"""Suite-configuration invariants that protect the offline, zero-cost guarantee."""

from __future__ import annotations

import pathlib
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_live_tests_deselected_by_default():
    """Live tests spend real (subscription) model calls; a bare `pytest` must never run them."""
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = cfg["tool"]["pytest"]["ini_options"].get("addopts", "")
    assert "not live" in addopts
