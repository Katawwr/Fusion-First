"""Owner decision (2026-09-29): Fusion is positioned as measure + guard; the prompt fix is optional and
carries its measured caveat. The README and the project guide must say so."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _intro(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n")
    return " ".join(text.split("\n## ")[0].split())  # the lead, before the first section, on one line


@pytest.mark.unit
def test_the_readme_leads_with_measure_and_guard():
    intro = _intro("README.md")
    assert "Measure and guard" in intro
    assert intro.index("runtime guardrail") < intro.index("prompt fix")
    assert "prompt fix is optional" in intro
    assert "rarely cut attacks" in intro


@pytest.mark.unit
def test_the_project_guide_names_the_guardrail_and_the_optional_fix():
    intro = _intro("CLAUDE.md")
    assert "runtime guardrail" in intro
    assert "prompt fix" in intro and "optional" in intro
