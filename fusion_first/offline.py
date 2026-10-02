"""The offline switch: FUSION_OFFLINE=1 hard-disables every real model call (CLI and Ollama).

The test suite sets it for every non-`live` test (tests/conftest.py), so an offline run can never
spawn the real `claude` CLI or touch a local model: no subscription quota is ever spent by a plain
`pytest`. It doubles as an air-gapped mode for users: set it and Fusion refuses real calls.
"""

from __future__ import annotations

import os

OFFLINE_ENV = "FUSION_OFFLINE"


def offline() -> bool:
    return os.environ.get(OFFLINE_ENV) == "1"
