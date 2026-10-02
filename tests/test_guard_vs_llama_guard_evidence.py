"""The committed Llama Guard comparison re-derives from its own rows and raw verdicts
(evals/validation/v1/PREREG_guard_vs_llama_guard.md). Offline; skipped until the evidence exists."""

from __future__ import annotations

import json
import pathlib

import pytest

from fusion_first.validate.llama_guard import parse_verdict, score

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evals/validation/v1/guard_vs_llama_guard.json"


@pytest.mark.unit
@pytest.mark.skipif(not EVIDENCE.exists(), reason="the comparison has not been committed yet")
def test_the_committed_comparison_re_derives_from_its_rows_and_raw_verdicts():
    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    raw = {}
    for line in (ROOT / ev["raw_verdicts"]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            raw[(r["config"], r["model"], r["item_id"])] = parse_verdict(r["output"])["label"]
    rows = []
    for r in ev["rows"]:
        assert raw[("a", r["model"], r["item_id"])] == r["lg_a"] and raw[("b", r["model"], r["item_id"])] == r["lg_b"]
        key = "stopped" if r["attack"] else "blocked_any"
        rows.append({**r, key: r["fusion"]})
    again = score(rows)
    for key in ("fusion", "llama_guard_a", "llama_guard_b", "union_fusion_b", "comparisons", "by_attack_type"):
        assert again[key] == ev[key], key
    assert (ev["fusion"]["all"]["stopped"], ev["fusion"]["all"]["attacks"]) == (50, 70)  # pinned rules a6fa0f5
