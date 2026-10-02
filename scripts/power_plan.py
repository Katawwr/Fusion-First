"""Sample sizes for the next evidence run, from effect sizes in committed evidence.

    python scripts/power_plan.py

Rates come from small models in evals/validation/v1: a stronger model that lands fewer attacks needs MORE
items than shown for the same number of attacks.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.stats.metrics import wilson_interval  # noqa: E402
from fusion_first.stats.power import mcnemar_power  # noqa: E402

V1 = ROOT / "evals/validation/v1"
GRID = (30, 60, 100, 150, 200, 300, 400, 600, 800)


def _needed(p_improve: float, p_regress: float, target: float = 0.8) -> int | None:
    for n in GRID:
        if mcnemar_power(n, p_improve, p_regress) >= target:
            return n
    return None


def main() -> int:
    ev = json.loads((V1 / "evidence_oracle.json").read_text(encoding="utf-8"))["pooled"]
    lg = json.loads((V1 / "guard_vs_llama_guard.json").read_text(encoding="utf-8"))
    rows = []

    def paired(label: str, b: int, c: int, n: int, harm: bool = False):
        p_i, p_r = (c / n, b / n) if harm else (b / n, c / n)
        power = {m: mcnemar_power(m, p_i, p_r) for m in (60, 100, 200, 400)}
        rows.append((label, f"{p_i:.3f} vs {p_r:.3f}", power, _needed(p_i, p_r)))

    atk_b = ev["injecagent"]["before_after"]["discordant_b"] + ev["gandalf"]["before_after"]["discordant_b"]
    atk_c = ev["injecagent"]["before_after"]["discordant_c"] + ev["gandalf"]["before_after"]["discordant_c"]
    atk_n = ev["injecagent"]["before_after"]["n_pairs"] + ev["gandalf"]["before_after"]["n_pairs"]
    paired("prompt fix: fewer attacks (items, pooled InjecAgent+Gandalf)", atk_b, atk_c, atk_n)
    xs = ev["xstest"]["before_after"]
    paired("prompt fix: more refusals of safe requests (XSTest items)", xs["discordant_b"], xs["discordant_c"],
           xs["n_pairs"], harm=True)
    cmp_b = lg["comparisons"]["fusion_vs_llama_guard_b"]["attacks"]
    n_att = lg["fusion"]["all"]["attacks"]
    paired("guard vs Llama Guard (configured): attacks stopped (successful attacks)",
           cmp_b["fusion_only"], cmp_b["other_only"], n_att)

    print("Paired questions: power at n pairs, and n for 80% power (None = over 800)\n")
    print("| question | improve vs regress rate | n=60 | n=100 | n=200 | n=400 | n for 80% |")
    print("|---|---|---|---|---|---|---|")
    for label, rates, power, need in rows:
        print(f"| {label} | {rates} | " + " | ".join(f"{power[m]:.0%}" for m in (60, 100, 200, 400))
              + f" | {need} |")

    print("\nGuard recall on successful attacks: Wilson 95% interval if 80% are stopped\n")
    print("| successful attacks | interval |")
    print("|---|---|")
    for k in (15, 30, 50, 80, 120):
        iv = wilson_interval(round(0.8 * k), k)
        print(f"| {k} | {iv.low:.0%} to {iv.high:.0%} |")

    print("\nWrongly blocked clean transcripts: upper 95% bound with 0 or 1 blocked\n")
    print("| clean transcripts | 0 blocked | 1 blocked |")
    print("|---|---|---|")
    for n in (40, 73, 100, 150, 250):
        print(f"| {n} | {wilson_interval(0, n).high:.1%} | {wilson_interval(1, n).high:.1%} |")

    print("\nItems needed per model for a number of successful attacks, by landing rate\n")
    print("| successful attacks | 10% land | 20% land | 30% land |")
    print("|---|---|---|---|")
    for k in (30, 50, 80):
        print(f"| {k} | " + " | ".join(str(round(k / r)) for r in (0.1, 0.2, 0.3)) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
