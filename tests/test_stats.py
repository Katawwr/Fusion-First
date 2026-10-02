"""Known-answer tests for the proof statistics, against hand-computed analytic values."""

from __future__ import annotations

import pytest

from fusion_first.schemas import Honesty
from fusion_first.stats.metrics import accuracy_result, cohen_kappa, confusion, wilson_interval
from fusion_first.stats.paired import before_after, mcnemar_exact_p, paired_bootstrap_diff

# ------------------------------- Bar A: metrics -------------------------------


@pytest.mark.unit
def test_wilson_interval_known_value():
    # p=0.5, n=100 -> Wilson 95% CI approx [0.4038, 0.5962]
    ci = wilson_interval(50, 100)
    assert ci.point == pytest.approx(0.5, abs=1e-9)
    assert ci.low == pytest.approx(0.4038, abs=1e-3)
    assert ci.high == pytest.approx(0.5962, abs=1e-3)


@pytest.mark.unit
def test_wilson_interval_extremes_stay_in_bounds():
    lo = wilson_interval(0, 10)
    hi = wilson_interval(10, 10)
    assert lo.low == 0.0 and 0.25 < lo.high < 0.35  # ~[0, 0.278]
    assert hi.high == pytest.approx(1.0) and 0.65 < hi.low < 0.75  # ~[0.722, 1]


@pytest.mark.unit
def test_confusion_matrix():
    y_true = [True, True, False, False]
    y_pred = [True, False, True, False]
    assert confusion(y_true, y_pred) == (1, 1, 1, 1)


@pytest.mark.unit
def test_cohen_kappa_known_value():
    # 2x2: both-yes=20, true-yes/pred-no=5(fn), true-no/pred-yes=10(fp), both-no=15 -> kappa=0.4
    y_true = [True] * 25 + [False] * 25
    y_pred = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    assert cohen_kappa(y_true, y_pred) == pytest.approx(0.4, abs=1e-9)


@pytest.mark.unit
def test_cohen_kappa_perfect_agreement():
    y = [True, False, True, True, False]
    assert cohen_kappa(y, y) == pytest.approx(1.0)


@pytest.mark.unit
def test_accuracy_result_perfect_judge():
    y_true = [True, False, True, False, True]
    res = accuracy_result(y_true, y_true, label_source="oracle:test")
    assert res.precision.point == 1.0
    assert res.recall.point == 1.0
    assert res.f1 == pytest.approx(1.0)
    assert res.cohen_kappa == pytest.approx(1.0)
    assert (res.tp, res.fp, res.tn, res.fn) == (3, 0, 2, 0)


# ------------------------------- Bar B: paired -------------------------------


@pytest.mark.unit
def test_mcnemar_all_improvements_is_significant():
    # b=10 improvements, c=0 regressions -> p = 2 * 0.5^10 = 0.001953
    assert mcnemar_exact_p(10, 0) == pytest.approx(2 * 0.5**10, abs=1e-6)


@pytest.mark.unit
def test_mcnemar_symmetric_is_not_significant():
    assert mcnemar_exact_p(5, 5) == pytest.approx(1.0)


@pytest.mark.unit
def test_mcnemar_no_discordant_pairs():
    assert mcnemar_exact_p(0, 0) == 1.0


@pytest.mark.unit
def test_paired_bootstrap_is_deterministic():
    base = [True] * 15 + [False] * 15
    hard = [False] * 30
    a = paired_bootstrap_diff(base, hard, n_boot=2000, seed=7)
    b = paired_bootstrap_diff(base, hard, n_boot=2000, seed=7)
    assert (a.point, a.low, a.high) == (b.point, b.low, b.high)
    assert a.point == pytest.approx(0.5, abs=1e-9)
    assert a.low > 0  # a real reduction should have a CI strictly above 0


@pytest.mark.unit
def test_before_after_strong_improvement_is_proven():
    # 25 probes fail on baseline, all pass after hardening -> clear, well-powered win
    base = [True] * 25 + [False] * 5
    hard = [False] * 30
    res = before_after(base, hard, n_boot=3000, seed=1)
    assert res.discordant_b == 25 and res.discordant_c == 0
    assert res.mcnemar_p < 0.05
    assert res.absolute_reduction.point == pytest.approx(25 / 30, abs=1e-9)
    assert res.honesty == Honesty.PROVEN


@pytest.mark.unit
def test_before_after_tiny_sample_is_not_overclaimed():
    # Only 3 probes, a directional but underpowered signal must NOT be stamped PROVEN
    base = [True, True, False]
    hard = [False, False, False]
    res = before_after(base, hard, n_boot=2000, seed=1)
    assert res.honesty in (Honesty.PRELIMINARY, Honesty.INCONCLUSIVE)
    assert res.honesty != Honesty.PROVEN


@pytest.mark.unit
def test_before_after_no_effect_is_inconclusive():
    base = [True, False] * 15
    hard = [True, False] * 15  # identical -> no discordant pairs
    res = before_after(base, hard, n_boot=2000, seed=1)
    assert res.honesty == Honesty.INCONCLUSIVE


@pytest.mark.unit
def test_empty_sample_is_never_graded_A():
    """0 scored pairs means nothing was measured: the grade is '?', never a flattering 'A'."""
    from fusion_first.engine.report import build_report_card

    card = build_report_card(
        target_name="t", check="direct_prompt_injection", judge_accuracy=None,
        before_after=before_after([], []), judge_model="m", gold_version="g",
        crosswalk_version="c", demonstration=False,
    )
    assert card.grade == "?"
    assert card.hardened_grade == "?"


@pytest.mark.unit
def test_honesty_reasons_explain_why_not_proven():
    small = before_after([True] * 8, [False] * 8)
    assert small.honesty.value != "PROVEN"
    assert any("at least 20 paired attacks (had 8)" in r for r in small.honesty_reasons)
    proven = before_after([True] * 25, [False] * 25)
    assert proven.honesty.value == "PROVEN" and proven.honesty_reasons == []
    none = before_after([False] * 25, [False] * 25)
    assert any("no measured reduction" in r for r in none.honesty_reasons)
