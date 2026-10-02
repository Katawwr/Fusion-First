from __future__ import annotations

import html

import pytest

from fusion_first.engine.report_html import render_dashboard_html, render_report_card_html
from fusion_first.schemas import (
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
        fix_title="Constrain consequential actions",
        fix_snippet="# --- Fusion First safety guardrails (auto-applied) ---\n## Constrain consequential actions\n- Only invoke a consequential tool ...",
        judge_model="demo-heuristic-judge",
        gold_version="abc123",
        crosswalk_version="def456",
        verification_hash="deadbeefdeadbeef",
        demonstration=demo,
    )


@pytest.mark.unit
def test_card_html_contains_key_values():
    h = render_report_card_html(_card())
    assert "Excessive agency" in h  # underscores humanized
    assert "LLM06" in h and "ASI02" in h
    assert "PRELIMINARY" in h
    assert "72%" in h  # reduction
    assert "verify deadbeefdeadbeef" in h


@pytest.mark.unit
def test_dashboard_leads_with_the_runtime_guardrail():
    page = render_dashboard_html([_card(), _card()], title="All checks")
    assert page.count("Runtime guardrail") == 1
    assert page.index("Runtime guardrail") < page.index('class="card"')
    assert "guard_tool_call(" in page and "GuardedModelClient(" in page
    assert "every check ships a fix" not in page


@pytest.mark.unit
def test_the_guardrail_block_states_the_in_sample_replay_when_the_scan_has_one():
    from fusion_first.engine.guard_replay import REPLAY_SETUP
    from fusion_first.schemas import ProbeOutcome

    def o(issue, replay):
        return ProbeOutcome(check="excessive_agency", probe_id=f"{issue}{replay}", attack_label="a",
                            baseline_issue=issue, hardened_issue=issue, guard_replay=replay)

    page = render_dashboard_html([_card()], outcomes=[o(True, "stopped"), o(True, "allowed"), o(False, "allowed")])
    assert "the guard blocked or redacted 1 of 2 attacks that got through and 0 of 1 reply graded clean" in page
    assert html.escape(REPLAY_SETUP) in page  # says how the replay's guard was set up
    assert page.index("In-sample") < page.index('class="card"')
    assert "In-sample" not in render_dashboard_html([_card()])  # no outcomes given
    assert "In-sample" not in render_dashboard_html([_card()], outcomes=[o(True, None)])  # demo: no verdicts
    withheld = _card()
    withheld.grade = "?"
    assert "In-sample" not in render_dashboard_html([withheld], outcomes=[o(True, "stopped")])  # grade withheld


@pytest.mark.unit
def test_the_summary_links_each_checks_grade_to_its_row():
    page = render_dashboard_html([_card()])
    assert '<a class="tile" href="#excessive_agency">' in page and 'id="excessive_agency"' in page
    assert page.index('class="tile"') < page.index("Runtime guardrail") < page.index('class="card"')


@pytest.mark.unit
def test_a_quality_only_report_has_no_guardrail_block():
    c = _card()
    c.kind, c.check = "quality", "instruction_following"
    assert "Runtime guardrail" not in render_dashboard_html([c])


@pytest.mark.unit
def test_the_fix_is_optional_and_its_measured_caveat_is_said_once():
    h = render_report_card_html(_card())
    assert "Optional: prompt fix" in h and "Apply this fix" not in h
    assert "As written" in h and "With fix" in h and "Hardened<" not in h
    page = render_dashboard_html([_card(), _card()])
    assert page.count("rarely cut attacks and raised refusals of safe requests") == 1


@pytest.mark.unit
def test_card_shows_copyable_fix_and_harden_command():
    h = render_report_card_html(_card(), idx=3)
    assert "Optional: prompt fix" in h
    assert "Constrain consequential actions" in h
    assert "safety guardrails" in h  # the snippet body
    assert 'onclick="fusionCopy(' in h and "Copy" in h  # copy button
    assert "fusion harden --prompt your_prompt.txt --check excessive_agency" in h  # auto-apply cmd


@pytest.mark.unit
def test_an_example_report_is_labelled_once_in_the_masthead():
    page = render_dashboard_html([_card(demo=True), _card(demo=True)])
    assert page.count("Example Report") == 1 and "Demonstration" not in page
    assert "Example Report" not in render_dashboard_html([_card(demo=False)])


@pytest.mark.unit
def test_the_report_uses_the_site_brand():
    page = render_dashboard_html([_card()])
    assert 'class="mark"' in page and "#504d9a" in page and "Fusion First" in page
    assert "#66c4e1" not in page  # the retired cyan wordmark
    assert chr(0x2014) not in page  # no em dashes


@pytest.mark.unit
def test_dashboard_is_clean_theme_aware_and_self_contained():
    page = render_dashboard_html([_card(), _card()], title="All checks")
    assert page.startswith("<!doctype html>")
    assert "Fusion" in page and "First" in page
    assert "gradient" not in page.lower()
    assert "--bg:" in page
    assert 'data-theme="light"' in page and "prefers-color-scheme:light" in page  # dark by default, like the site
    for bad in ("http://", "https://", "src=", "<link", "cdn.", "//fonts"):
        assert bad not in page
    assert page.count('class="card"') == 2


@pytest.mark.unit
def test_html_escapes_untrusted_fields():
    c = _card()
    c.target_name = "<script>alert(1)</script>"
    c.top_fixes = ["<img src=x onerror=alert(1)>"]
    c.fix_snippet = "<b>not html</b>"
    h = render_report_card_html(c)
    assert "<script>alert(1)" not in h
    assert "<img src=x" not in h
    assert "<b>not html</b>" not in h  # snippet escaped
