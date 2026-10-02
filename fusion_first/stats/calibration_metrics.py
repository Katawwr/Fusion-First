"""Probability calibration: Brier, ECE, reliability bins and Platt scaling (pure Python, deterministic)."""

from __future__ import annotations

import math
from dataclasses import dataclass


def brier(probs: list[float], labels: list[bool]) -> float:
    if not probs:
        return 0.0
    return sum((p - (1.0 if y else 0.0)) ** 2 for p, y in zip(probs, labels, strict=True)) / len(probs)


def brier_skill(probs: list[float], labels: list[bool]) -> float:
    """1 - Brier / Brier(base rate): > 0 means better than always predicting the base rate."""
    if not labels:
        return 0.0
    base = sum(labels) / len(labels)
    ref = brier([base] * len(labels), labels)
    return 1.0 - brier(probs, labels) / ref if ref > 0 else 0.0


@dataclass(frozen=True)
class ReliabilityBin:
    lo: float
    hi: float
    n: int
    mean_prob: float
    frac_positive: float


def reliability_bins(
    probs: list[float], labels: list[bool], n_bins: int = 10, strategy: str = "uniform"
) -> list[ReliabilityBin]:
    """Group predictions into bins (uniform width, or equal-count 'quantile') and compare the mean
    predicted probability with the observed positive rate in each."""
    pairs = sorted(zip(probs, labels, strict=True))
    if not pairs:
        return []
    groups: list[list[tuple[float, bool]]] = []
    if strategy == "quantile":
        size = max(1, math.ceil(len(pairs) / n_bins))
        groups = [pairs[i : i + size] for i in range(0, len(pairs), size)]
    elif strategy == "uniform":
        for k in range(n_bins):
            lo, hi = k / n_bins, (k + 1) / n_bins
            last = k == n_bins - 1
            g = [(p, y) for p, y in pairs if lo <= p < hi or (last and p >= hi)]
            if g:
                groups.append(g)
    else:
        raise ValueError("strategy must be 'uniform' or 'quantile'")
    out = []
    for g in groups:
        ps = [p for p, _ in g]
        out.append(
            ReliabilityBin(
                lo=min(ps),
                hi=max(ps),
                n=len(g),
                mean_prob=sum(ps) / len(g),
                frac_positive=sum(1 for _, y in g if y) / len(g),
            )
        )
    return out


def expected_calibration_error(
    probs: list[float], labels: list[bool], n_bins: int = 10, strategy: str = "uniform"
) -> float:
    bins = reliability_bins(probs, labels, n_bins, strategy)
    n = len(probs)
    return sum(b.n / n * abs(b.mean_prob - b.frac_positive) for b in bins) if n else 0.0


@dataclass(frozen=True)
class PlattScaler:
    a: float
    b: float

    def __call__(self, score: float) -> float:
        z = self.a * score + self.b
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)


def fit_platt(scores: list[float], labels: list[bool], iters: int = 100, l2: float = 1e-3) -> PlattScaler:
    """Fit p = sigmoid(a*score + b) by Newton's method with a tiny ridge (stable on separable data).
    Fit on the DEV split only; apply unchanged to blind."""
    a, b = 1.0, 0.0
    ys = [1.0 if y else 0.0 for y in labels]
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(scores, ys, strict=True):
            p = PlattScaler(a, b)(x)
            w = p * (1 - p)
            ga += (p - y) * x
            gb += p - y
            haa += w * x * x
            hab += w * x
            hbb += w
        ga += l2 * a
        haa += l2
        hbb += l2
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) < 1e-9 and abs(db) < 1e-9:
            break
    return PlattScaler(a, b)
