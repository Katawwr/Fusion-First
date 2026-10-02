"""Every image the landing page's link-preview tags point at must ship in frontend/public."""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_link_preview_images_exist():
    landing = (ROOT / "frontend/src/pages/Landing.jsx").read_text(encoding="utf-8")
    images = re.findall(r'(?:og|twitter):image"\s+content="https?://[^/"]+(/[^"]+)"', landing)
    assert images, "the landing page declares no link-preview image"
    for path in images:
        assert (ROOT / "frontend/public" / path.lstrip("/")).is_file(), f"{path} is referenced but missing"
