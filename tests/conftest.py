"""Suite-wide safety: offline tests can never make a real model call.

Every test not marked `live` runs with FUSION_OFFLINE=1, which makes the claude CLI and Ollama
clients refuse to run and report themselves unavailable. So no plain `pytest` run can spend
subscription quota or depend on a local model — even if a code path unexpectedly goes live.
"""

from __future__ import annotations

import pytest

from fusion.offline import OFFLINE_ENV


@pytest.fixture(autouse=True)
def _offline_unless_live(request, monkeypatch):
    if "live" not in request.node.keywords:
        monkeypatch.setenv(OFFLINE_ENV, "1")
    yield
