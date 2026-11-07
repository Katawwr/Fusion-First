"""docs/CASE_STUDY.md: the reviewer-facing one-pager. Linked from the top of the README, it states the headline guard
result, the not-adopted detector study and the AI-assisted workflow, and quotes only registered numbers."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASE = "docs/CASE_STUDY.md"


def _text() -> str:
    return " ".join((ROOT / CASE).read_text(encoding="utf-8").split())


@pytest.mark.unit
def test_the_readme_links_the_case_study_before_its_first_section():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    lead = readme.split("\n## ")[0]
    line = next(x for x in lead.splitlines() if CASE in x)
    assert "Case study" in line and not re.search(r"\d", re.sub(r"<[^>]+>", "", line))


@pytest.mark.unit
def test_the_case_study_quotes_registered_claims_for_its_numbers():
    from fusion_first.validate.claims import load_registry

    text = _text()
    mine = {c["id"]: c["text"] for c in load_registry().claims if CASE in (c.get("files") or [])}
    assert {"runtime_guardrail_step2_recall", "llama_guard_step2_recall", "runtime_guardrail_step2_overblock",
            "detector_v1_primary_injecagent_recall", "detector_v1_decision",
            "detector_v1_shipped_in_source_injecagent", "judge_toolloop_accuracy"} <= set(mine)
    assert all(t in text for t in mine.values())


@pytest.mark.unit
def test_the_case_study_states_the_negative_result_the_method_and_the_workflow():
    from fusion_first.validate.prereg import detector_decision

    env = json.loads((ROOT / "evals/validation/v1/detector/detector_v1.json").read_text(encoding="utf-8"))
    text = _text()
    assert not detector_decision(env)["adopt"] and "not adopted" in text
    for phrase in ("pre-registered", "sealed", "evals/claims.yaml", "PREREG_LEDGER.md", "Co-Authored-By",
                   "in-source", "leave-one-source-out", "grades prose", "tool loop"):
        assert phrase in text, phrase


@pytest.mark.unit
def test_the_case_study_ships_the_loop_and_states_how_gold_v2_was_authored_and_graded():
    text = _text()
    assert "is the next build" not in text and "authored blind" not in text
    for phrase in ("The tool loop now ships for excessive agency and exfiltration: `--corpus v2`", "bounded loop",
                   "scripted tool results", "cross-checks the grader against the oracle on those real calls",
                   "is a Quick-tier sample of one 7B model: read its intervals, not its points",
                   "static authored trajectories, not a model's own replies; no target behaviour measured",
                   "wrote to the oracle's own rules with the intended label in mind",
                   "hard negatives that quote the instruction and decline), not on ambiguous ones",
                   "The answer key was in the repository during grading",
                   "so the guarantee is procedural, not technical"):
        assert phrase in text, phrase
    assert chr(0x2014) not in text
