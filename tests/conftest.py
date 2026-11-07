"""Every test not marked `live` runs with FUSION_OFFLINE=1, so the claude CLI and Ollama clients
refuse to run: no plain `pytest` run can spend subscription quota or depend on a local model."""

from __future__ import annotations

import pytest

from fusion_first.offline import OFFLINE_ENV


@pytest.fixture(autouse=True)
def _offline_unless_live(request, monkeypatch):
    if "live" not in request.node.keywords:
        monkeypatch.setenv(OFFLINE_ENV, "1")
    yield


@pytest.fixture
def v2_fixture_probes(monkeypatch):
    """The 3-row v2 test fixture (attack, payload split, benign control) loaded as the excessive_agency
    corpus v2; the template cache is cleared around the test so nothing leaks."""
    from pathlib import Path

    from fusion_first.attacks import templates as templates_mod
    from fusion_first.attacks.templates import get_templates

    monkeypatch.setattr(templates_mod, "PROBE_DIR", Path(__file__).parent / "fixtures" / "probes_v2")
    get_templates.cache_clear()
    yield get_templates("excessive_agency", "v2")
    get_templates.cache_clear()
