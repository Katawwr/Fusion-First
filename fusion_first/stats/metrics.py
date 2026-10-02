"""Bar A statistics: judge-vs-oracle accuracy.

Wilson intervals (well-behaved at small n and the extremes). Cohen's kappa alongside accuracy, since
a judge on an imbalanced set can look accurate while barely beating chance.
"""

from __future__ import annotations

import math

from fusion_first.schemas import AccuracyResult, Interval

Z_95 = 1.959963984540054  # z for a two-sided 95% interval


def wilson_interval(successes: int, n: int, z: float = Z_95) -> Interval:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return Interval(point=0.0, low=0.0, high=1.0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return Interval(point=p, low=max(0.0, center - half), high=min(1.0, center + half))


def confusion(y_true: list[bool], y_pred: list[bool]) -> tuple[int, int, int, int]:
    """Return (tp, fp, tn, fn) treating True as the positive (is-issue) class."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    tp = fp = tn = fn = 0
    for t, p in zip(y_true, y_pred, strict=True):
        if t and p:
            tp += 1
        elif not t and p:
            fp += 1
        elif not t and not p:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def cohen_kappa(y_true: list[bool], y_pred: list[bool]) -> float:
    """Cohen's kappa for two binary raters (oracle vs judge)."""
    n = len(y_true)
    if n == 0:
        return 0.0
    tp, fp, tn, fn = confusion(y_true, y_pred)
    po = (tp + tn) / n
    p_true_pos = (tp + fn) / n
    p_pred_pos = (tp + fp) / n
    pe = p_true_pos * p_pred_pos + (1 - p_true_pos) * (1 - p_pred_pos)
    if pe == 1.0:
        return 1.0  # both raters constant and agreeing
    return (po - pe) / (1 - pe)


def accuracy_result(
    y_true: list[bool], y_pred: list[bool], label_source: str = "oracle"
) -> AccuracyResult:
    """Compute the full Bar-A result from oracle labels (y_true) and judge verdicts (y_pred)."""
    n = len(y_true)
    tp, fp, tn, fn = confusion(y_true, y_pred)
    precision = wilson_interval(tp, tp + fp) if (tp + fp) else Interval(point=0, low=0, high=1)
    recall = wilson_interval(tp, tp + fn) if (tp + fn) else Interval(point=0, low=0, high=1)
    p, r = precision.point, recall.point
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return AccuracyResult(
        n=n,
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=wilson_interval(tp + tn, n),
        cohen_kappa=cohen_kappa(y_true, y_pred),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        label_source=label_source,
    )


# Validation statistics (Trust Report): sample sizes, balanced accuracy, bootstrap CIs, agreement.


def wilson_halfwidth(p: float, n: int, z: float = Z_95) -> float:
    """Half-width of the Wilson interval at proportion `p` with `n` trials (continuous in p)."""
    if n <= 0:
        return 0.5
    z2 = z * z
    denom = 1 + z2 / n
    return (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))


def required_n_for_halfwidth(p: float, halfwidth: float, z: float = Z_95, n_max: int = 100_000) -> int:
    """Smallest n whose Wilson interval at proportion p has half-width <= `halfwidth`.
    e.g. p=0.9, h=0.15 -> 17 per class: a blind split needs ~17 positives AND ~17 negatives."""
    for n in range(1, n_max + 1):
        if wilson_halfwidth(p, n, z) <= halfwidth:
            return n
    raise ValueError("half-width not reachable within n_max")


def specificity(y_true: list[bool], y_pred: list[bool]) -> Interval:
    tp, fp, tn, fn = confusion(y_true, y_pred)
    return wilson_interval(tn, tn + fp) if (tn + fp) else Interval(point=0, low=0, high=1)


def balanced_accuracy(y_true: list[bool], y_pred: list[bool]) -> float:
    """Mean of recall and specificity: robust to class imbalance (unlike raw accuracy)."""
    tp, fp, tn, fn = confusion(y_true, y_pred)
    parts = []
    if tp + fn:
        parts.append(tp / (tp + fn))
    if tn + fp:
        parts.append(tn / (tn + fp))
    return sum(parts) / len(parts) if parts else 0.0


def f1_score(y_true: list[bool], y_pred: list[bool]) -> float:
    tp, fp, tn, fn = confusion(y_true, y_pred)
    return (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else 0.0


def bootstrap_ci(
    y_true: list[bool],
    y_pred: list[bool],
    stat,
    n_boot: int = 2000,
    seed: int = 7,
    alpha: float = 0.05,
) -> Interval:
    """Percentile bootstrap CI for `stat(y_true, y_pred)`, resampling items; deterministic given `seed`."""
    import random

    n = len(y_true)
    point = stat(y_true, y_pred)
    if n == 0:
        return Interval(point=point, low=point, high=point)
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(stat([y_true[i] for i in idx], [y_pred[i] for i in idx]))
    vals.sort()
    lo = vals[int((alpha / 2) * (n_boot - 1))]
    hi = vals[int((1 - alpha / 2) * (n_boot - 1))]
    return Interval(point=point, low=lo, high=hi)


def fleiss_kappa(ratings: list[list[bool]]) -> float:
    """Fleiss' kappa for binary ratings: ratings[i] = the verdicts of all raters on item i.
    Every item must have the same number of raters (>= 2)."""
    if not ratings:
        return 0.0
    m = len(ratings[0])
    if m < 2 or any(len(r) != m for r in ratings):
        raise ValueError("every item needs the same number (>= 2) of ratings")
    n = len(ratings)
    p_yes = sum(sum(r) for r in ratings) / (n * m)
    p_e = p_yes ** 2 + (1 - p_yes) ** 2
    p_bar = sum(
        (sum(r) * (sum(r) - 1) + (m - sum(r)) * (m - sum(r) - 1)) / (m * (m - 1)) for r in ratings
    ) / n
    if p_e == 1.0:
        return 1.0
    return (p_bar - p_e) / (1 - p_e)


def flip_rate(runs: list[list[bool]]) -> Interval:
    """Share of items whose verdict differs across repeated runs (runs[k][i]), with a Wilson interval."""
    if not runs:
        return Interval(point=0, low=0, high=1)
    n = len(runs[0])
    if any(len(r) != n for r in runs):
        raise ValueError("every run must cover the same items")
    flips = sum(1 for i in range(n) if len({run[i] for run in runs}) > 1)
    return wilson_interval(flips, n)


def mcnemar_classifiers(
    y_true: list[bool], pred_a: list[bool], pred_b: list[bool]
) -> tuple[int, int, float]:
    """Paired comparison of two classifiers: (a_right_b_wrong, b_right_a_wrong, exact McNemar p)."""
    from fusion_first.stats.paired import mcnemar_exact_p

    b = sum(1 for t, a, bb in zip(y_true, pred_a, pred_b, strict=True) if a == t and bb != t)
    c = sum(1 for t, a, bb in zip(y_true, pred_a, pred_b, strict=True) if a != t and bb == t)
    return b, c, mcnemar_exact_p(b, c)
