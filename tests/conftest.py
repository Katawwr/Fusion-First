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
