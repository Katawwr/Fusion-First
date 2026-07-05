"""Bar A statistics: judge-vs-oracle accuracy.

All intervals are Wilson score intervals (well-behaved at the extremes and small n, unlike
the normal approximation). Cohen's kappa is reported alongside raw accuracy because a judge
on an imbalanced set can look accurate while barely beating chance.
"""

from __future__ import annotations

import math

from fusion.schemas import AccuracyResult, Interval

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
