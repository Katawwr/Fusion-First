"""Known-answer tests for the validation statistics behind the Trust Report."""

from __future__ import annotations

import pytest

from fusion_first.stats.calibration_metrics import (
    brier,
    brier_skill,
    expected_calibration_error,
    fit_platt,
    reliability_bins,
)
from fusion_first.stats.metrics import (
    balanced_accuracy,
    bootstrap_ci,
    cohen_kappa,
    f1_score,
    fleiss_kappa,
    flip_rate,
    mcnemar_classifiers,
    required_n_for_halfwidth,
    specificity,
    wilson_halfwidth,
)
from fusion_first.stats.paired import (
    cluster_bootstrap_diff,
    mcnemar_exact_p,
    noninferiority,
)
from fusion_first.stats.power import mcnemar_power


@pytest.mark.unit
def test_required_n_matches_the_design_calculation():
    # Wilson half-width <= 0.15 at p = 0.9 needs 17 per class (16 gives ~0.153).
    assert required_n_for_halfwidth(0.9, 0.15) == 17
    assert wilson_halfwidth(0.9, 16) > 0.15 >= wilson_halfwidth(0.9, 17)


@pytest.mark.unit
@pytest.mark.parametrize(("b", "c"), [(0, 0), (1, 0), (5, 1), (12, 2), (10, 10), (3, 17), (40, 25)])
def test_exact_mcnemar_matches_scipy(b, c):
    scipy_stats = pytest.importorskip("scipy.stats")
    n = b + c
    expected = 1.0 if n == 0 else scipy_stats.binomtest(min(b, c), n, 0.5).pvalue
    assert mcnemar_exact_p(b, c) == pytest.approx(expected, abs=1e-12)


@pytest.mark.unit
def test_balanced_accuracy_and_specificity():
    y = [True, True, True, True, False, False, False, False, False, False]
    p = [True, True, True, False, False, False, False, False, False, True]
    assert balanced_accuracy(y, p) == pytest.approx((3 / 4 + 5 / 6) / 2)
    assert specificity(y, p).point == pytest.approx(5 / 6)
    assert f1_score(y, p) == pytest.approx(2 * 3 / (2 * 3 + 1 + 1))


@pytest.mark.unit
def test_bootstrap_ci_brackets_the_point_and_is_deterministic():
    y = [True] * 10 + [False] * 10
    p = [True] * 8 + [False] * 2 + [False] * 9 + [True]
    a = bootstrap_ci(y, p, cohen_kappa, n_boot=500, seed=3)
    b = bootstrap_ci(y, p, cohen_kappa, n_boot=500, seed=3)
    assert a == b
    assert a.low <= a.point <= a.high


@pytest.mark.unit
def test_fleiss_kappa_perfect_and_chance():
    assert fleiss_kappa([[True, True, True], [False, False, False]]) == pytest.approx(1.0)
    split = [[True, False], [False, True], [True, False], [False, True]]
    assert fleiss_kappa(split) < 0


@pytest.mark.unit
def test_flip_rate_counts_items_that_changed_across_runs():
    runs = [[True, True, False, False], [True, False, False, False], [True, True, False, True]]
    fr = flip_rate(runs)
    assert fr.point == pytest.approx(2 / 4)


@pytest.mark.unit
def test_mcnemar_classifiers_counts_discordant_correctness():
    y = [True, True, False, False, True]
    a = [True, True, False, False, False]  # right on 4
    b = [False, False, False, True, False]  # right on 1
    ab, ba, p = mcnemar_classifiers(y, a, b)
    assert (ab, ba) == (3, 0)
    assert p == pytest.approx(0.25)


@pytest.mark.unit
def test_calibration_metrics():
    probs = [0.1, 0.1, 0.9, 0.9] * 25
    labels = [False, False, True, True] * 25
    assert brier(probs, labels) == pytest.approx(0.01)
    assert brier_skill(probs, labels) > 0.9
    # perfectly calibrated bins: 30% predicted, 30% observed
    cal_p = [0.3] * 10
    cal_y = [True] * 3 + [False] * 7
    assert expected_calibration_error(cal_p, cal_y) == pytest.approx(0.0)
    assert expected_calibration_error([0.9] * 10, [False] * 10) == pytest.approx(0.9)
    bins = reliability_bins(probs, labels, n_bins=5, strategy="quantile")
    assert sum(b.n for b in bins) == len(probs)


@pytest.mark.unit
def test_platt_scaling_is_monotone_and_calibrates():
    scores = [0.05, 0.1, 0.2, 0.3, 0.6, 0.7, 0.8, 0.95] * 10
    labels = [False, False, False, True, False, True, True, True] * 10
    s = fit_platt(scores, labels)
    assert s(0.9) > s(0.5) > s(0.1)
    calibrated = [s(x) for x in scores]
    assert expected_calibration_error(calibrated, labels) < expected_calibration_error(scores, labels) + 1e-9


@pytest.mark.unit
def test_noninferiority_detects_a_harmful_fix():
    before = [True] * 40
    after_fine = [True] * 39 + [False]
    after_bad = [True] * 28 + [False] * 12
    _, ok = noninferiority(before, after_fine, margin=0.10)
    drop, bad_ok = noninferiority(before, after_bad, margin=0.10)
    assert ok is True
    assert bad_ok is False and drop.point == pytest.approx(0.30)


@pytest.mark.unit
def test_noninferiority_bound_exactly_at_the_margin_passes_despite_float_error():
    # 10 pairs: 1 hurt by the fix, 4 helped, 1 bad either way, 4 fine either way. The upper 95% bound
    # of the drop is exactly 1/10, but float subtraction lands at 0.10000000000000003.
    before = [True] + [False] * 4 + [False] + [True] * 4
    after = [False] + [True] * 4 + [False] + [True] * 4
    drop, ok = noninferiority(before, after, margin=0.10)
    assert drop.high == pytest.approx(0.10)
    assert ok is True  # "upper bound <= margin" is decided on the value, not its float rounding


@pytest.mark.unit
def test_cluster_bootstrap_is_wider_than_pairwise_when_clusters_correlate():
    from fusion_first.stats.paired import paired_bootstrap_diff

    # 10 attacks x 4 targets; each attack either always improves or never does (correlated).
    base, hard, clusters = [], [], []
    for a in range(10):
        improves = a < 6
        for _t in range(4):
            base.append(True)
            hard.append(not improves)
            clusters.append(f"attack{a}")
    pairwise = paired_bootstrap_diff(base, hard)
    clustered = cluster_bootstrap_diff(base, hard, clusters)
    assert clustered.point == pytest.approx(pairwise.point)
    assert (clustered.high - clustered.low) > (pairwise.high - pairwise.low)


@pytest.mark.unit
def test_power_grows_with_sample_size():
    small = mcnemar_power(18, p_improve=0.3, p_regress=0.05, n_sim=400)
    large = mcnemar_power(160, p_improve=0.3, p_regress=0.05, n_sim=400)
    assert large > small
    assert large > 0.95
