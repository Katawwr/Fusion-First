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


@pytest.mark.unit
def test_slow_tests_deselected_by_default_and_the_marker_is_registered():
    """Slow tests load a real local model; a bare `pytest` skips them, `-m slow` runs them."""
    ini = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert "not slow" in ini.get("addopts", "")
    assert any(m.split(":")[0].strip() == "slow" for m in ini.get("markers", []))
