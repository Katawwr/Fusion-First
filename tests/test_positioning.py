"""Positioning: measure + guard; the README leads with the site and how to use it, while results and caveats
live on the site and in the Trust Report."""

from __future__ import annotations

import re
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
def test_the_readme_gives_a_reviewer_a_path_before_any_detail():
    """Start here (case study, the verify command, the Trust Report and its ledger, the architecture) comes before
    the verify section; the verify section shows what a pass prints and points at the examples' own README; the
    registered studies sit after Use; every command uses the installed `fusion` entry point."""
    text = (ROOT / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    order = [text.index(h) for h in ("\n## Start here\n", "\n## Verify a real run\n", "\n## Use\n",
                                     "\n## Registered studies\n", "\n## License\n")]
    assert order == sorted(order)
    start = text.split("\n## Start here\n")[1].split("\n## ")[0]
    for link in ("docs/CASE_STUDY.md", "TRUST_REPORT.md", "evals/validation/v1/PREREG_LEDGER.md",
                 "docs/ARCHITECTURE.md"):
        assert f"]({link})" in start and (ROOT / link).is_file(), link
    verify = text.split("\n## Verify a real run\n")[1].split("\n## ")[0]
    assert "verified: result re-derived exactly" in verify and "](examples/README.md)" in verify
    assert "python -m fusion_first.cli" not in text
    assert "demo.gif" not in text and not (ROOT / "docs" / "img" / "demo.gif").exists()  # no recording (owner)


@pytest.mark.unit
def test_the_examples_readme_names_every_committed_run_and_how_to_verify_it():
    import json

    text = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    runs = sorted((ROOT / "examples").glob("*/.fusion/runs/*/plan.json"))
    assert len(runs) >= 3
    for plan_path in runs:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        row = next(line for line in text.splitlines() if f"`{plan['run_id']}`" in line)
        assert plan["target_model"] in row and plan["tier"].capitalize() in row
        assert f"version {plan['judge_prompt_version']}" in row
        assert f"fusion run verify --workspace examples/{plan_path.parents[3].name} {plan['run_id']}" in text
    assert chr(0x2014) not in text and "%" not in text  # card numbers stay in each run's result.json


@pytest.mark.unit
def test_no_agent_plan_is_tracked_under_docs():
    """Implementation plans written for coding agents are local working files, not reviewer-facing docs."""
    import subprocess

    tracked = subprocess.run(["git", "ls-files", "docs/design/plans"], cwd=ROOT, capture_output=True, text=True)
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")
    assert tracked.stdout.strip() == ""
    for doc in (ROOT / "docs").rglob("*.md"):
        if "plans" not in doc.parts:
            assert "docs/design/plans/" not in doc.read_text(encoding="utf-8"), doc


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


DETECTOR_EVIDENCE = "evals/validation/v1/detector/detector_v1.json"


@pytest.mark.unit
def test_the_detector_doc_quotes_only_its_registered_result():
    """docs/DETECTOR.md's registered-result section is a placeholder until the evidence is committed; once it is, the
    section cites the evidence file, states the registered verdict, carries the per-arm table exactly as generated from
    the evidence, and every number it quotes in prose is a registered claim. The "why" quotes the phrase list's
    registered numbers on the sealed rows (one claim per source), no longer the diagnostic re-run; the adaptive,
    in-distribution, dev-only and in-source limits stay stated."""
    import json

    from fusion_first.validate.claims import load_registry
    from fusion_first.validate.prereg import detector_decision
    from fusion_first.validate.trust_report import detector_doc_table

    text = (ROOT / "docs" / "DETECTOR.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    result = text.split("## Registered result")[1].split("\n## ")[0]
    if not (ROOT / DETECTOR_EVIDENCE).is_file():
        assert f"Filled when `{DETECTOR_EVIDENCE}` is committed" in result
        assert "%" not in result and " of " not in result and not re.search(r"\b0\.\d", result)  # no rate, no count
    else:
        envelope = json.loads((ROOT / DETECTOR_EVIDENCE).read_text(encoding="utf-8"))
        assert f"[`{DETECTOR_EVIDENCE}`](../{DETECTOR_EVIDENCE})" in result and "Filled when" not in result
        verdict = ("adopted as an observe-only `guard_input` signal" if detector_decision(envelope)["adopt"]
                   else "not adopted; the detector stays dev-only")
        assert f"Registered decision: {verdict}." in result
        assert detector_doc_table(envelope) in result
        claims = [c for c in load_registry().claims if "docs/DETECTOR.md" in (c.get("files") or [])]
        assert {c["evidence"] for c in claims} == {DETECTOR_EVIDENCE}
        assert all(c.get("min_n") == 50 and c.get("demonstration_ok") is False and c.get("n_path") for c in claims)
        prose = [line for line in result.splitlines() if not line.startswith("|")]
        quoted = [c["text"] for c in claims if any(c["text"] in line for line in prose)]
        assert len(quoted) == 4  # the two primaries, the phrase list on the same rows, the decision
        # the "why": the phrase list's registered recall per sealed source, each its own claim on the B1 arm's rows
        why = " ".join(text.split("## Why train one")[1].split("\n## ")[0].split())
        sealed = [c for c in claims if c["text"] not in quoted]
        assert len(sealed) == 3 and all(c["text"] in why for c in sealed)
        assert {p.split(".")[3] for c in sealed for p in c["metrics"]} == {"injecagent", "deepset", "bipia"}
        assert all(p.startswith("arms.b1_phrase_list.per_source.") for c in sealed for p in c["metrics"])
        assert "On the sealed confirmatory rows the list flagged" in why and "re-run" not in why
        assert "diagnostic, not registered" not in text
        for recon in ("1,054", "8 of 263", "0 of 200"):  # the dev re-run's counts, which the claims scanner would miss
            assert recon not in text
    for phrase in ("adaptive", "in-distribution", "dev-only", "in-source"):
        assert phrase in text
    assert chr(0x2014) not in text and "DETECTOR.md" in (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")


def _detector_doc() -> str:
    return " ".join((ROOT / "docs" / "DETECTOR.md").read_text(encoding="utf-8").split())


@pytest.mark.unit
@pytest.mark.skipif(not (ROOT / DETECTOR_EVIDENCE).is_file(), reason="the confirmatory pass is not committed yet")
def test_the_detector_doc_scopes_its_claims_to_what_was_measured():
    """The shipped model's false-positive rate and the phrase list's row are claimed, so the doc never says in its own
    voice that only leave-one-source-out numbers are claimed: it quotes the registration's words verbatim and gives
    the reading (LOSO recall is the only generalisation claim) as its own (R24). The phrase list had no registered
    evidence before this study; it has one now."""
    text = _detector_doc()
    quote = "only the LOSO numbers are claimed"
    assert quote in (ROOT / "evals/validation/v1/PREREG_detector_v1.md").read_text(encoding="utf-8")
    assert "Only leave-one-source-out numbers are claimed" not in text
    assert (f"The registration's words are \"{quote}\"; this doc reads them as: leave-one-source-out recall is the only "
            "generalisation claim; the shipped model's false-positive rate and the baselines' rows are registered "
            "measurements on the sealed rows and say nothing about unseen sources.") in text
    assert "The list has no registered evidence" not in text
    assert "had no registered evidence before this study" in text and "(#registered-result)" in text


@pytest.mark.unit
@pytest.mark.skipif(not (ROOT / DETECTOR_EVIDENCE).is_file(), reason="the confirmatory pass is not committed yet")
def test_the_detector_doc_names_where_the_registered_secondaries_live():
    """McNemar against the phrase list, per-technique recall and p50/p95 latency are registered secondaries held in the
    envelope and rendered in the Trust Report (Q5): the doc names their paths, says where they are rendered, and each
    path resolves in the committed envelope."""
    import json

    env = json.loads((ROOT / DETECTOR_EVIDENCE).read_text(encoding="utf-8"))
    text = _detector_doc()
    for path in ("`mcnemar_vs_phrase_list.<arm>.pooled`", "`.per_source`", "`arms.<arm>.per_technique`",
                 "`arms.<arm>.latency.p50_ms`", "`.p95_ms`"):
        assert path in text
    assert "it is not the bar" in text and "Neither is rendered" not in text
    assert 'The Trust Report (Q5) renders both under "Registered secondaries"' in text
    assert "per-category rates stay in the envelope" in text and "and in the Trust Report (Q5)" in text
    arms = env["arms"]
    assert set(env["mcnemar_vs_phrase_list"]) == set(arms) - {"b1_phrase_list"}
    assert all({"pooled", "per_source"} <= set(m) for m in env["mcnemar_vs_phrase_list"].values())
    assert all("per_technique" in a for a in arms.values())
    timed = {k for k, a in arms.items() if a.get("latency")}
    assert all({"p50_ms", "p95_ms"} <= set(arms[k]["latency"]) for k in timed)
    assert set(arms) - timed == {"b0_always_negative", "embed", "finetune"}  # B0 and the fold arms: none of their own


@pytest.mark.unit
@pytest.mark.skipif(not (ROOT / DETECTOR_EVIDENCE).is_file(), reason="the confirmatory pass is not committed yet")
def test_the_readme_states_the_detector_outcome_without_numbers():
    import json

    from fusion_first.validate.prereg import detector_decision

    env = json.loads((ROOT / DETECTOR_EVIDENCE).read_text(encoding="utf-8"))
    line = next(x for x in (ROOT / "README.md").read_text(encoding="utf-8").splitlines() if "docs/DETECTOR.md" in x)
    words = re.sub(r"<[^>]+>", "", line)
    outcome = "adopted as an observe-only signal" if detector_decision(env)["adopt"] else "not adopted"
    assert outcome in words and ("dev-only" in words) is not detector_decision(env)["adopt"]
    assert not re.search(r"\d", words)  # no numbers in the README: they live on the site and in the Trust Report


TOOLLOOP_EVIDENCE = "evals/validation/v1/toolloop/judge_eval_toolloop_host_sonnet.json"


@pytest.mark.unit
def test_the_readme_states_the_toolloop_judge_outcome_without_numbers():
    """The registered judge-accuracy result on tool trajectories: the README links the registration and states the
    decision's outcome in words; the numbers live on the site, in the Trust Report (Q6) and the case study."""
    import json

    from fusion_first.validate.prereg import toolloop_decision

    env = json.loads((ROOT / TOOLLOOP_EVIDENCE).read_text(encoding="utf-8"))
    line = next(x for x in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
                if "PREREG_q1_toolloop.md" in x)
    words = re.sub(r"<[^>]+>", "", line)
    outcome = ("it met its registered bar" if toolloop_decision(env)["claim_allowed"]
               else "it missed its registered bar, so no accuracy is claimed")
    assert "tool trajectories" in words and f"(registered result: {outcome})" in words and "Trust page" in words
    assert not re.search(r"\d", words)


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
