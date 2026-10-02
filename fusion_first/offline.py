"""FUSION_OFFLINE=1 hard-disables every real model call (tests/conftest.py sets it for non-`live` tests)."""

from __future__ import annotations

import os

OFFLINE_ENV = "FUSION_OFFLINE"


def offline() -> bool:
    return os.environ.get(OFFLINE_ENV) == "1"
