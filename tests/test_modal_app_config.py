"""The hosted API (app/modal_app.py) is the public demo: it carries no secrets, so no provider key can reach
it and nothing it runs is metered (zero spend). Read as text: importing it would need `modal`."""

from __future__ import annotations

from pathlib import Path

import pytest

SRC = (Path(__file__).resolve().parents[1] / "app" / "modal_app.py").read_text(encoding="utf-8")


@pytest.mark.unit
def test_the_hosted_api_attaches_no_secrets():
    assert "Secret.from_name" not in SRC and "secrets=" not in SRC


@pytest.mark.unit
def test_the_hosted_api_states_its_version_as_plain_config():
    assert '.env({"VERSION"' in SRC
