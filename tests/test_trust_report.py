"""TRUST_REPORT.md is generated from committed evidence — it must equal a fresh render."""

from __future__ import annotations

import pathlib

import pytest

from fusion.validate.trust_report import render

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_trust_report_matches_its_evidence():
    committed = (ROOT / "TRUST_REPORT.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == render(ROOT), "regenerate with: python -m fusion.validate.trust_report"


@pytest.mark.unit
def test_demo_evidence_never_reaches_the_report(tmp_path):
    (tmp_path / "evals/guard_bench").mkdir(parents=True)
    (tmp_path / "evals/guard_bench/claude_code_heldout_v1.json").write_text(
        '{"demonstration": true, "benign": {"n": 1}}', encoding="utf-8")
    out = render(tmp_path)
    assert "NOT YET MEASURED" in out and "| v1 |" not in out


@pytest.mark.unit
def test_website_evidence_matches_its_sources():
    import json

    from fusion.validate.trust_report import evidence_json

    committed = json.loads((ROOT / "frontend/src/content/evidence.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(evidence_json(ROOT))), \
        "regenerate with: python -m fusion.validate.trust_report"
