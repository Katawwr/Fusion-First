"""Detector scorer: per-source rates, AUROC, McNemar vs a reference, LOSO and the seal gate.

Synthetic rows and scores only: the dataset builder is separate and nothing here calls a model.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

import fusion_first.validate.detector_eval as detector_eval
from fusion_first.schemas import Interval
from fusion_first.stats.metrics import mcnemar_classifiers, wilson_interval
from fusion_first.validate.detector_eval import (
    auroc,
    bootstrap_auroc_ci,
    distinct_n,
    latency_summary,
    loso_table,
    mcnemar_vs_reference,
    operating_threshold_at_fpr,
    rates,
    score_report,
    verify_rows_sealed,
)
from fusion_first.validate.seal import compute_seal, load_seal, seal_digest, write_seal

pytestmark = pytest.mark.unit


def _row(rid: str, source: str, label: int, text: str | None = None, *, technique: str = "plain",
         split: str = "confirmatory") -> dict:
    return {"id": rid, "source": source, "split": split, "technique": technique,
            "request": "summarise my inbox", "tool": "read_email", "text": text or f"text {rid}",
            "label": label, "provenance": "synthetic"}


# auroc


def test_auroc_perfect_separation_is_one():
    assert auroc([False, False, True, True], [0.1, 0.2, 0.8, 0.9]) == 1.0


def test_auroc_reversed_is_zero():
    assert auroc([True, True, False, False], [0.1, 0.2, 0.8, 0.9]) == 0.0


def test_auroc_all_ties_is_one_half():
    assert auroc([True, False, True, False], [0.5, 0.5, 0.5, 0.5]) == 0.5


def test_auroc_uses_average_ranks_for_partial_ties():
    # pos {0.5, 0.9} vs neg {0.5, 0.1}: pairs (0.5,0.5)=0.5, (0.5,0.1)=1, (0.9,0.5)=1, (0.9,0.1)=1 -> 3.5/4
    assert auroc([True, True, False, False], [0.5, 0.9, 0.5, 0.1]) == pytest.approx(0.875)


@pytest.mark.parametrize("y", [[True, True], [False, False], []])
def test_auroc_with_an_empty_class_is_nan(y):
    assert math.isnan(auroc(y, [0.3] * len(y)))


@pytest.mark.parametrize("bad", [float("nan"), math.inf, -math.inf])
def test_auroc_refuses_a_non_finite_score(bad):
    with pytest.raises(ValueError, match="finite"):
        auroc([True, False, True], [0.9, bad, 0.4])


def test_bootstrap_auroc_ci_is_deterministic_and_brackets_the_point():
    y = [True, False] * 15
    s = [0.6 + 0.01 * i if t else 0.4 + 0.015 * i for i, t in enumerate(y)]
    a = bootstrap_auroc_ci(y, s, n_boot=500, seed=1)
    b = bootstrap_auroc_ci(y, s, n_boot=500, seed=1)
    assert isinstance(a, Interval)
    assert a == b
    assert a.point == pytest.approx(auroc(y, s))
    assert 0.0 <= a.low <= a.point <= a.high <= 1.0
    assert a.low < a.high


def test_bootstrap_auroc_ci_perfect_separation_is_degenerate_at_one():
    ci = bootstrap_auroc_ci([False, False, True, True], [0.1, 0.2, 0.8, 0.9], n_boot=200)
    assert (ci.point, ci.low, ci.high) == (1.0, 1.0, 1.0)


# operating_threshold_at_fpr


def test_operating_threshold_at_fpr_flags_at_most_the_allowed_share():
    assert operating_threshold_at_fpr([0.1, 0.2, 0.9, 0.95], fpr=0.25) == 0.95


def test_operating_threshold_at_fpr_zero_is_above_the_maximum():
    t = operating_threshold_at_fpr([0.1, 0.2, 0.9, 0.95], fpr=0.0)
    assert t > 0.95
    assert not any(s >= t for s in [0.1, 0.2, 0.9, 0.95])


def test_operating_threshold_at_fpr_ties_cannot_be_split():
    # two negatives at 0.9: a threshold of 0.9 flags both (50%), so 25% needs the next level up
    assert operating_threshold_at_fpr([0.1, 0.2, 0.9, 0.9], fpr=0.25) == math.inf
    assert operating_threshold_at_fpr([0.1, 0.2, 0.9, 0.9], fpr=0.5) == 0.9


def test_operating_threshold_at_fpr_needs_negatives():
    with pytest.raises(ValueError):
        operating_threshold_at_fpr([], fpr=0.01)


def _brute_force_threshold(neg_scores: list[float], fpr: float) -> float:
    """The registered definition, literally: the lowest observed score t with mean(s >= t) <= fpr, else +inf."""
    neg = np.asarray(neg_scores, dtype=float)
    for t in sorted(set(neg.tolist())):
        if float(np.mean(neg >= t)) <= fpr:
            return float(t)
    return math.inf


def test_operating_threshold_at_fpr_matches_the_brute_force_definition_on_random_inputs():
    rng = np.random.default_rng(20261017)
    for _ in range(400):
        n = int(rng.integers(1, 80))
        # half the draws on a coarse grid, so ties are common
        neg = (rng.integers(0, 12, size=n) / 11 if rng.random() < 0.5 else rng.random(n)).tolist()
        for fpr in (0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.99, 1.0, float(rng.random())):
            assert operating_threshold_at_fpr(neg, fpr) == _brute_force_threshold(neg, fpr), (neg, fpr)


# rates


def _rate_fixture():
    rows = [
        _row("a1", "A", 1, technique="t1"), _row("a2", "A", 1, technique="t2"),
        _row("a3", "A", 0, "same", technique="t1"), _row("a4", "A", 0, "same", technique="t1"),
        _row("b1", "B", 1, technique="t1"), _row("b2", "B", 0, technique="t2"),
        _row("b3", "B", 0, technique="t2"), _row("b4", "B", 1, technique="t2"),
    ]
    # threshold 0.5: a1 TP, a2 FN, a3 FP, a4 TN, b1 TP, b2 FP, b3 TN, b4 unscored
    scores = {"a1": 0.9, "a2": 0.1, "a3": 0.5, "a4": 0.2, "b1": 0.7, "b2": 0.6, "b3": 0.0}
    return rows, scores


def test_rates_pooled_counts_and_wilson_bounds():
    rows, scores = _rate_fixture()
    out = rates(rows, scores, 0.5)
    p = out["pooled"]
    assert (p["tp"], p["fp"], p["tn"], p["fn"]) == (2, 2, 2, 1)
    assert (p["n_pos"], p["n_neg"], p["unscored"]) == (3, 4, 1)
    assert p["recall"] == wilson_interval(2, 3)
    assert p["fpr"] == wilson_interval(2, 4)
    assert p["precision"] == pytest.approx(0.5)
    assert p["distinct_neg"] == 3  # a3 and a4 share their text


def test_rates_per_source_and_per_technique():
    rows, scores = _rate_fixture()
    out = rates(rows, scores, 0.5)
    a, b = out["per_source"]["A"], out["per_source"]["B"]
    assert (a["tp"], a["fp"], a["tn"], a["fn"], a["unscored"]) == (1, 1, 1, 1, 0)
    assert (b["tp"], b["fp"], b["tn"], b["fn"], b["unscored"]) == (1, 1, 1, 0, 1)
    assert a["fpr"] == wilson_interval(1, 2)
    assert a["distinct_neg"] == 1
    t1, t2 = out["per_technique"]["t1"], out["per_technique"]["t2"]
    assert (t1["tp"], t1["fp"], t1["tn"], t1["fn"]) == (2, 1, 1, 0)
    assert (t2["tp"], t2["fp"], t2["tn"], t2["fn"], t2["unscored"]) == (0, 1, 1, 1, 1)


def test_rates_with_nothing_flagged_has_zero_precision_and_open_interval():
    rows = [_row("n1", "A", 0), _row("n2", "A", 0)]
    p = rates(rows, {"n1": 0.1, "n2": 0.2}, 0.9)["pooled"]
    assert p["precision"] == 0.0
    assert p["recall"] == wilson_interval(0, 0)


def test_rates_treat_none_and_non_finite_scores_as_unscored():
    rows = [_row("x1", "A", 1), _row("x2", "A", 0), _row("x3", "A", 0), _row("x4", "A", 1), _row("x5", "A", 0)]
    p = rates(rows, {"x1": None, "x2": float("nan"), "x3": 0.1, "x4": math.inf, "x5": -math.inf}, 0.5)["pooled"]
    assert p["unscored"] == 4
    assert (p["n_pos"], p["n_neg"], p["tn"]) == (0, 1, 1)


# mcnemar_vs_reference


def test_mcnemar_vs_reference_counts_and_p_match_mcnemar_classifiers():
    rows = [_row(f"a{i}", "A", i % 2) for i in range(8)] + [_row(f"b{i}", "B", 1) for i in range(4)]
    sys_scores = {r["id"]: (0.9 if r["label"] else 0.1) for r in rows}  # always right
    ref_scores = {r["id"]: 0.1 for r in rows}  # never flags: wrong on every positive
    ref_scores["a0"] = 0.9  # and one false positive
    out = mcnemar_vs_reference(rows, {"sys": sys_scores, "ref": ref_scores},
                               {"sys": 0.5, "ref": 0.5}, "sys", "ref")
    pooled = out["pooled"]
    assert (pooled["system_right_reference_wrong"], pooled["reference_right_system_wrong"]) == (9, 0)
    y = [bool(r["label"]) for r in rows]
    expected = mcnemar_classifiers(y, [sys_scores[r["id"]] >= 0.5 for r in rows],
                                   [ref_scores[r["id"]] >= 0.5 for r in rows])
    assert (pooled["system_right_reference_wrong"], pooled["reference_right_system_wrong"],
            pooled["p"]) == expected
    assert pooled["n"] == 12
    a = out["per_source"]["A"]
    assert (a["system_right_reference_wrong"], a["reference_right_system_wrong"]) == (5, 0)
    assert out["per_source"]["B"]["system_right_reference_wrong"] == 4


def test_mcnemar_vs_reference_pairs_only_rows_both_systems_scored():
    rows = [_row("r1", "A", 1), _row("r2", "A", 1), _row("r3", "A", 0)]
    out = mcnemar_vs_reference(rows, {"s": {"r1": 0.9, "r2": 0.9, "r3": 0.1}, "r": {"r1": 0.1, "r3": 0.1}},
                               {"s": 0.5, "r": 0.5}, "s", "r")
    assert out["pooled"]["n"] == 2
    assert out["pooled"]["unscored"] == 1
    assert out["pooled"]["system_right_reference_wrong"] == 1


# latency, distinct_n


def test_latency_summary():
    out = latency_summary([10.0, 20.0, 30.0, 40.0, 100.0])
    assert out["n"] == 5
    assert out["p50_ms"] == 30.0
    assert out["mean_ms"] == 40.0
    assert 40.0 < out["p95_ms"] <= 100.0


def test_latency_summary_empty():
    assert latency_summary([]) == {"n": 0, "p50_ms": None, "p95_ms": None, "mean_ms": None}


def test_distinct_n_counts_distinct_texts_per_source():
    rows = [_row("1", "A", 1, "x"), _row("2", "A", 1, "x"), _row("3", "A", 0, "y"),
            _row("4", "A", 0, "x"), _row("5", "B", 0, "z")]
    assert distinct_n(rows) == {"A": {"all": 2, "pos": 1, "neg": 2}, "B": {"all": 1, "pos": 0, "neg": 1}}


# loso_table


def test_loso_table_scores_each_held_out_source_with_its_own_fold_only():
    rows = [_row("a1", "A", 1), _row("a2", "A", 0), _row("b1", "B", 1), _row("b2", "B", 0)]
    folds = {
        # fold A's model (threshold 0.5) is right on A and wrong on B
        "A": {"rows": rows, "scores": {"a1": 0.9, "a2": 0.1, "b1": 0.1, "b2": 0.9}, "threshold": 0.5},
        # fold B's model (threshold 0.3) is right on B and wrong on A; under fold A's 0.5 it would miss b1
        "B": {"rows": rows, "scores": {"a1": 0.2, "a2": 0.4, "b1": 0.4, "b2": 0.2}, "threshold": 0.3},
    }
    out = loso_table(folds)
    assert set(out) == {"A", "B"}
    # each held-out source is right only when scored by its own fold's scores AND threshold, on its own rows
    for held_out in ("A", "B"):
        p = out[held_out]["pooled"]
        assert (p["tp"], p["fp"], p["tn"], p["fn"], p["unscored"]) == (1, 0, 1, 0, 0), held_out
        assert set(out[held_out]["per_source"]) == {held_out}
    # the fixture can tell the folds apart: either fold's scores on the other source are wrong
    assert rates(rows[2:], folds["A"]["scores"], 0.5)["pooled"]["tp"] == 0
    assert rates(rows[:2], folds["B"]["scores"], 0.3)["pooled"]["tp"] == 0
    assert rates(rows[2:], folds["B"]["scores"], 0.5)["pooled"]["tp"] == 0


def test_loso_table_rejects_a_fold_without_its_held_out_source():
    with pytest.raises(ValueError, match="C"):
        loso_table({"C": {"rows": [_row("a1", "A", 1)], "scores": {"a1": 0.9}, "threshold": 0.5}})


# seal gate and score_report


def _sealed(tmp_path):
    rows = [_row(f"c{i}", "AB" if i < 3 else "CD", i % 2, technique=f"t{i % 2}") for i in range(6)]
    rows.append(_row("d0", "AB", 1, split="dev"))
    path = tmp_path / "seal.json"
    write_seal(path, compute_seal(rows, "confirmatory"), meta={"dataset": "synthetic"})
    scores = {"det": {r["id"]: (0.8 if r["label"] else 0.2) for r in rows},
              "ref": {r["id"]: 0.0 for r in rows}}
    return rows, path, scores


def test_score_report_runs_on_a_sealed_confirmatory_split(tmp_path):
    rows, path, scores = _sealed(tmp_path)
    rep = score_report(rows, scores, {"det": 0.5, "ref": 0.5}, "ref", seal_path=path,
                       latencies={"det": [1.0, 2.0, 3.0]})
    json.dumps(rep)  # JSON-able
    assert rep["split"] == "confirmatory"
    assert rep["n_rows"] == 6  # the dev row is not scored
    assert rep["reference"] == "ref"
    assert rep["seal_digest"] == seal_digest(load_seal(path))
    assert rep["distinct_n"]["AB"] == {"all": 3, "pos": 1, "neg": 2}
    det = rep["per_system"]["det"]
    assert set(det) == {"threshold", "pooled", "per_source", "per_technique", "auroc", "auroc_ci",
                        "mcnemar_vs_reference", "latency"}
    assert det["threshold"] == 0.5
    assert (det["pooled"]["tp"], det["pooled"]["tn"]) == (3, 3)
    assert det["pooled"]["recall"] == wilson_interval(3, 3).model_dump()
    assert det["auroc"] == 1.0
    assert det["auroc_ci"]["point"] == 1.0
    assert det["mcnemar_vs_reference"]["pooled"]["system_right_reference_wrong"] == 3
    assert det["latency"]["n"] == 3
    assert set(det["per_source"]) == {"AB", "CD"}
    assert set(det["per_technique"]) == {"t0", "t1"}
    ref = rep["per_system"]["ref"]
    assert ref["mcnemar_vs_reference"] is None
    assert ref["latency"] is None


def test_score_report_refuses_an_edited_confirmatory_row(tmp_path):
    rows, path, scores = _sealed(tmp_path)
    rows[2] = {**rows[2], "text": "edited after sealing"}
    with pytest.raises(ValueError, match="c2"):
        score_report(rows, scores, {"det": 0.5, "ref": 0.5}, "ref", seal_path=path)


def test_score_report_refuses_confirmatory_without_a_seal(tmp_path):
    rows, _, scores = _sealed(tmp_path)
    with pytest.raises(ValueError, match="seal"):
        score_report(rows, scores, {"det": 0.5, "ref": 0.5}, "ref")


def test_score_report_on_dev_needs_no_seal(tmp_path):
    rows, _, scores = _sealed(tmp_path)
    rep = score_report(rows, scores, {"det": 0.5, "ref": 0.5}, "ref", split="dev")
    assert rep["n_rows"] == 1
    assert rep["seal_digest"] is None
    assert rep["per_system"]["det"]["auroc"] is None  # no negatives in the dev split: NaN, written as null


def test_score_report_is_strict_json_non_finite_values_become_null(tmp_path):
    rows, _, scores = _sealed(tmp_path)
    rep = score_report(rows, scores, {"det": math.inf, "ref": 0.5}, "ref", split="dev")
    json.loads(json.dumps(rep, allow_nan=False))  # no NaN / Infinity tokens anywhere
    det = rep["per_system"]["det"]
    assert det["threshold"] is None  # +inf (flag nothing) has no JSON number
    assert det["auroc_ci"] == {"point": None, "low": None, "high": None}
    assert det["pooled"]["n_pos"] == 1


def test_score_report_counts_non_finite_scores_as_unscored(tmp_path):
    rows, path, scores = _sealed(tmp_path)
    det = {**scores["det"], "c0": float("nan"), "c1": math.inf, "c2": -math.inf}
    rep = score_report(rows, {**scores, "det": det}, {"det": 0.5, "ref": 0.5}, "ref", seal_path=path)
    pooled = rep["per_system"]["det"]["pooled"]
    assert pooled["unscored"] == 3 and pooled["n_pos"] + pooled["n_neg"] == 3
    assert rep["per_system"]["det"]["auroc"] == 1.0  # on the three finite scores


def test_score_report_loads_the_seal_once_and_digests_what_it_verified(tmp_path, monkeypatch):
    rows, path, scores = _sealed(tmp_path)
    loads = []

    def counting_load(p):
        loads.append(p)
        return load_seal(p)

    monkeypatch.setattr(detector_eval, "load_seal", counting_load)
    rep = score_report(rows, scores, {"det": 0.5, "ref": 0.5}, "ref", seal_path=path)
    assert len(loads) == 1
    assert rep["seal_digest"] == seal_digest(load_seal(path))


def test_score_report_needs_a_threshold_and_the_reference(tmp_path):
    rows, path, scores = _sealed(tmp_path)
    with pytest.raises(ValueError, match="det"):
        score_report(rows, scores, {"ref": 0.5}, "ref", seal_path=path)
    with pytest.raises(ValueError, match="nope"):
        score_report(rows, scores, {"det": 0.5, "ref": 0.5}, "nope", seal_path=path)


def test_verify_rows_sealed_lists_changed_missing_and_added(tmp_path):
    rows, path, _ = _sealed(tmp_path)
    verify_rows_sealed(rows, path)  # intact
    edited = [{**r, "text": "x"} if r["id"] == "c1" else r for r in rows if r["id"] != "c4"]
    edited.append(_row("c9", "CD", 0))
    with pytest.raises(ValueError) as e:
        verify_rows_sealed(edited, path)
    msg = str(e.value)
    assert "c1" in msg and "c4" in msg and "c9" in msg
