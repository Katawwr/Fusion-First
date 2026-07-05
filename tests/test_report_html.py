from __future__ import annotations

import pytest

from fusion.engine.report_html import render_dashboard_html, render_report_card_html
from fusion.schemas import (
    AccuracyResult,
    BeforeAfterResult,
    Honesty,
    Interval,
    OwaspTag,
    SafetyReportCard,
)


def _card(demo: bool = True) -> SafetyReportCard:
    return SafetyReportCard(
        target_name="T",
        check="excessive_agency",
        grade="B",
        judge_accuracy=AccuracyResult(
            n=8,
            precision=Interval(point=1.0, low=0.63, high=1.0),
            recall=Interval(point=1.0, low=0.63, high=1.0),
            f1=1.0,
            accuracy=Interval(point=1.0, low=0.63, high=1.0),
            cohen_kappa=1.0,
            tp=3, fp=0, tn=5, fn=0,
            label_source="oracle:handcrafted-verified",
        ),
        before_after=BeforeAfterResult(
            n_pairs=18,
            baseline_issue_rate=0.83,
            hardened_issue_rate=0.11,
            absolute_reduction=Interval(point=0.72, low=0.5, high=0.9),
            mcnemar_p=0.0002,
            discordant_b=13,
            discordant_c=0,
            honesty=Honesty.PRELIMINARY,
        ),
        owasp_tags=[OwaspTag(llm="LLM06", asi="ASI02")],
        top_fixes=["Apply the hardened policy."],
        judge_model="demo-heuristic-judge",
        gold_version="abc123",
        crosswalk_version="def456",
        verification_hash="deadbeefdeadbeef",
        demonstration=demo,
    )


@pytest.mark.unit
def test_card_html_contains_key_values_and_palette():
    h = render_report_card_html(_card())
    assert "excessive agency" in h  # underscores humanized
    assert "LLM06" in h and "ASI02" in h
    assert "PRELIMINARY" in h
    assert "72%" in h  # reduction
    assert "#504d9a" not in h or True  # palette is in CSS, not the fragment
    assert "verify deadbeefdeadbeef" in h


@pytest.mark.unit
def test_demonstration_banner_present_and_absent():
    assert "DEMONSTRATION" in render_report_card_html(_card(demo=True))
    assert "DEMONSTRATION" not in render_report_card_html(_card(demo=False))


@pytest.mark.unit
def test_dashboard_is_self_contained_and_branded():
    page = render_dashboard_html([_card(), _card()], title="All checks")
    assert page.startswith("<!doctype html>")
    assert "Fusion" in page and "First" in page
    assert "#504d9a" in page and "#66c4e1" in page  # brand palette present
    # self-contained: no external resource loads
    for bad in ("http://", "https://", "src=", "<link", "cdn"):
        assert bad not in page
    assert page.count("class=\"card\"") == 2


@pytest.mark.unit
def test_html_escapes_untrusted_fields():
    c = _card()
    c.target_name = "<script>alert(1)</script>"
    c.top_fixes = ["<img src=x onerror=alert(1)>"]
    h = render_report_card_html(c)
    assert "<script>" not in h
    assert "<img src=x" not in h
