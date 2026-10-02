"""Positioning: measure + guard; the README leads with the site and how to use it, while results and caveats
live on the site and in the Trust Report."""

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
    assert "Measure and guard" in intro and "runtime guardrail" in intro
    assert "harden" not in intro and "prompt fix" not in intro  # the optional fix is not a headline


@pytest.mark.unit
def test_the_readme_shows_the_site_then_how_to_use_it():
    """No Results section; a dark screenshot of the home page, linked to the site, near the top."""
    text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "## Results" not in text and "-light.png" not in text
    shot = text.index("docs/img/overview-dark.png")
    assert text.rindex('<a href="https://fusion-first-testing.com">', 0, shot) < shot < text.index("## Use")
    mcp = text[text.index("**MCP**"):]
    assert "guardrail_snippet" in mcp[:300]
    assert text.rstrip().endswith("## License MIT") and (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


@pytest.mark.unit
def test_the_ci_hint_offers_the_guardrail_before_the_fix():
    text = (ROOT / "integrations" / "README.md").read_text(encoding="utf-8")
    hint = next(line for line in text.splitlines() if "exit 1 = a check is below the bar" in line)
    assert hint.index("runtime guardrail") < hint.index("fusion harden")


@pytest.mark.unit
@pytest.mark.skipif(not (ROOT / "CLAUDE.md").exists(), reason="the coding-agent guide is local, not in the repository")
def test_the_project_guide_names_the_guardrail_and_the_optional_fix():
    intro = _intro("CLAUDE.md")
    assert "runtime guardrail" in intro
    assert "prompt fix" in intro and "optional" in intro


@pytest.mark.unit
def test_the_docs_describe_the_in_sample_guard_replay():
    arch = " ".join((ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8").split())
    assert "in-sample" in arch
    audit = (ROOT / "plugins" / "fusion" / "skills" / "audit" / "SKILL.md").read_text(encoding="utf-8")
    assert "guard_in_sample" in audit and "in-sample" in audit


@pytest.mark.unit
def test_no_doc_says_wrapping_the_client_is_the_whole_guard():
    client = (ROOT / "fusion_first" / "guardrail" / "client.py").read_text(encoding="utf-8")
    assert "full runtime protection" not in client
    integrations = (ROOT / "integrations" / "README.md").read_text(encoding="utf-8")
    assert "wrap the model client with the guardrail." not in integrations


def _card(baseline: list[bool], hardened: list[bool]):
    from fusion_first.engine.report import build_report_card
    from fusion_first.stats.paired import before_after

    return build_report_card(target_name="t", check="system_prompt_leakage", judge_accuracy=None,
                             before_after=before_after(baseline, hardened), judge_model="m",
                             gold_version="g", crosswalk_version="c", demonstration=False)


@pytest.mark.unit
def test_a_card_whose_attacks_got_through_leads_with_the_guardrail_and_the_fix_second():
    """`top_fixes[0]` is the `top_fix` of `fusion run finalize` and the MCP scan tools."""
    card = _card([True] * 6 + [False] * 2, [True] + [False] * 7)  # 75% -> 12%: the fix helped here
    assert "runtime guardrail" in card.top_fixes[0]
    assert card.top_fixes[1].startswith("Optional prompt fix") and "PRELIMINARY" in card.top_fixes[1]


@pytest.mark.unit
def test_a_prompt_fix_that_raised_the_issue_rate_is_flagged_not_suggested():
    card = _card([True] * 2 + [False] * 6, [True] * 5 + [False] * 3)  # 25% -> 62%, as llama3.2:1b did live
    assert "runtime guardrail" in card.top_fixes[0]
    assert "raised the issue rate" in card.top_fixes[1]
    assert not any(f.startswith("Optional prompt fix") for f in card.top_fixes)


@pytest.mark.unit
def test_a_check_nothing_got_through_recommends_nothing():
    assert _card([False] * 8, [False] * 8).top_fixes == []
