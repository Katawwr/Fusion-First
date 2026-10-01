"""Step 3 (evals/validation/v1/PREREG_step3_guard.md): the same rules with and without the untrusted text, on
fresh InjecAgent transcripts. The sample is disjoint from every spent one; the decision is the registered one."""

from __future__ import annotations

import pathlib
import runpy

import pytest

from fusion_first.validate.experiments import SPENT, SPENT_THROUGH_STEP2, build_items

ROOT = pathlib.Path(__file__).resolve().parents[1]
STEP3 = runpy.run_path(str(ROOT / "scripts/step3_guard.py"), run_name="step3")


@pytest.mark.unit
def test_the_step3_sample_is_disjoint_from_every_spent_sample():
    fresh = {it.item_id for it in build_items("injecagent", STEP3["N"], salt=STEP3["SALT"], exclude=SPENT_THROUGH_STEP2)}
    spent = {it.item_id for spec in SPENT for it in build_items(
        "injecagent", spec[1], salt=spec[0], exclude=spec[2] if len(spec) > 2 else None)}
    spent |= {it.item_id for it in build_items("injecagent", 100, salt="fusion-evidence-step2-v1", exclude=SPENT)}
    assert len(fresh) == STEP3["N"] and not fresh & spent


def _rows(attack_pairs, clean_pairs):
    """(v2, v3) stopped per attack; (v2, v3) wrongly blocked per clean transcript."""
    rows = [{"model": "m", "item_id": f"a{i}", "kind": "ds", "attack": True, "v2": a, "v3": b}
            for i, (a, b) in enumerate(attack_pairs)]
    rows += [{"model": "m", "item_id": f"c{i}", "kind": "dh", "attack": False, "v2": a, "v3": b}
             for i, (a, b) in enumerate(clean_pairs)]
    return rows


@pytest.mark.unit
def test_adopted_when_significantly_more_attacks_stopped_and_no_more_clean_blocked():
    s = STEP3["score_rows"](_rows([(False, True)] * 12 + [(True, True)] * 40, [(False, False)] * 150))
    assert s["comparisons"]["attacks"]["p"] < 0.05
    assert s["decision"] == "adopted"
    assert s["v3"]["all"]["stopped"] == 52 and s["v2"]["all"]["stopped"] == 40


@pytest.mark.unit
def test_not_adopted_without_a_significant_gain():
    s = STEP3["score_rows"](_rows([(False, True)] * 4 + [(True, True)] * 40, [(False, False)] * 150))
    assert s["decision"] == "not adopted"


EVIDENCE = ROOT / "evals/validation/v1/step3_guard.json"


@pytest.mark.unit
@pytest.mark.skipif(not EVIDENCE.exists(), reason="step 3 has not been scored yet")
def test_the_committed_step3_result_re_derives_from_its_rows():
    import json

    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    again = STEP3["score_rows"](ev["rows"])
    for key in ("v2", "v3", "comparisons", "decision", "decision_inputs"):
        assert again[key] == ev[key], key
    assert ev["guardrail_git_sha"] == STEP3["RULES_SHA"] and ev["sample"]["n"] == STEP3["N"]


@pytest.mark.integration
@pytest.mark.skipif(not EVIDENCE.exists(), reason="step 3 has not been scored yet")
def test_the_committed_rows_re_derive_from_the_committed_transcripts():
    import json

    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert STEP3["rows"]() == ev["rows"]


@pytest.mark.unit
def test_not_adopted_when_it_blocks_more_clean_transcripts_than_registered():
    extra = STEP3["MAX_EXTRA_CLEAN_BLOCKED"] + 1
    s = STEP3["score_rows"](_rows([(False, True)] * 20, [(False, True)] * extra + [(False, False)] * 150))
    assert s["decision"] == "not adopted"
