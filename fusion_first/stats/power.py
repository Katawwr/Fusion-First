"""Simulated McNemar power: can a before/after design reach PROVEN at a given sample size?"""

from __future__ import annotations

import random

from fusion_first.stats.paired import mcnemar_exact_p


def mcnemar_power(
    n_pairs: int,
    p_improve: float,
    p_regress: float,
    alpha: float = 0.05,
    n_sim: int = 2000,
    seed: int = 11,
) -> float:
    """P(exact McNemar p < alpha, in the improving direction) when each pair independently improves
    with prob `p_improve`, regresses with `p_regress`, and is otherwise concordant."""
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_sim):
        b = c = 0
        for _ in range(n_pairs):
            u = rng.random()
            if u < p_improve:
                b += 1
            elif u < p_improve + p_regress:
                c += 1
        if b > c and mcnemar_exact_p(b, c) < alpha:
            hits += 1
    return hits / n_sim
