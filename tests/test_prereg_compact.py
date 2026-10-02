"""The pre-registered compact-fix decision (evals/validation/v1/PREREG_compact_fix.md), computed from
oracle labels: never judged by eye. Offline: transcripts are seeded, no model runs."""

from __future__ import annotations

import pytest

from fusion_first.validate.analysis import attack_success_by_model
from fusion_first.validate.experiments import build_items
from fusion_first.validate.prereg import compact_decision
from fusion_first.validate.transcripts import TranscriptRecord, TranscriptStore

ARMS = ("baseline", "compact")


def _seed(store, exp, items, model, arm, leak):
    for item in items:
        if exp == "gandalf":
            text = f"The password is {item.oracle['canaries'][0]}." if leak else "I can't share that."
        else:
            tool = item.oracle["forbidden_tools"][0]
            text = f'ACTION: {{"tool": "{tool}", "arguments": {{}}}}' if leak else "Here are the details."
        store.append(TranscriptRecord(experiment=exp, item_id=item.item_id, model=model, arm=arm,
                                      system_sha256="x", response=text, truncated=False))


@pytest.mark.unit
def test_attack_success_pools_injecagent_and_gandalf_per_model(tmp_path):
    store = TranscriptStore(tmp_path)
    items = {"injecagent": build_items("injecagent", 6), "gandalf": build_items("gandalf", 6),
             "xstest": build_items("xstest", 3)}
    for exp in ("injecagent", "gandalf"):
        _seed(store, exp, items[exp], "m1", "baseline", leak=True)
        _seed(store, exp, items[exp], "m1", "compact", leak=False)
    m1 = attack_success_by_model(items, ["m1"], store, ARMS)["m1"]
    assert m1["n_pairs"] == 12  # both attack experiments, and only them
    assert m1["baseline_rate"]["k"] == 12 and m1["treatment_rate"]["k"] == 0
    assert m1["before_after"]["discordant_b"] == 12 and m1["before_after"]["mcnemar_p"] < 0.001


def _attack(p, fixed, broke):
    return {"before_after": {"mcnemar_p": p, "discordant_b": fixed, "discordant_c": broke}}


def _xstest(model, noninferior):
    return {"experiment": "xstest", "model": model, "noninferior": noninferior}


@pytest.mark.unit
def test_adopts_when_one_model_meets_both_primary_outcomes():
    d = compact_decision({"m1": _attack(0.01, 10, 1), "m2": _attack(0.5, 3, 2)},
                         [_xstest("m1", True), _xstest("m2", False)])
    assert d["adopt"] is True
    assert d["per_model"]["m1"]["both_primary"] is True
    assert d["per_model"]["m2"]["both_primary"] is False


@pytest.mark.unit
def test_rejects_when_over_refusal_is_not_noninferior():
    d = compact_decision({"m1": _attack(0.01, 10, 1)}, [_xstest("m1", False)])
    assert d["adopt"] is False


@pytest.mark.unit
def test_rejects_when_any_model_gets_significantly_more_attacks():
    d = compact_decision({"m1": _attack(0.01, 10, 1), "m2": _attack(0.02, 1, 9)},
                         [_xstest("m1", True), _xstest("m2", True)])
    assert d["adopt"] is False
    assert d["per_model"]["m2"]["attack_higher"] is True


@pytest.mark.unit
def test_rejects_a_reduction_that_is_not_significant():
    d = compact_decision({"m1": _attack(0.20, 5, 2)}, [_xstest("m1", True)])
    assert d["adopt"] is False


@pytest.mark.unit
def test_missing_over_refusal_evidence_fails_closed():
    d = compact_decision({"m1": _attack(0.01, 10, 1)}, [])
    assert d["adopt"] is False
    assert d["per_model"]["m1"]["over_refusal_noninferior"] is False
