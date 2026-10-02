"""The committed step-2 result re-derives from its rows, the old rules' outcomes and the raw Llama Guard
verdicts (evals/validation/v1/PREREG_step2_guard.md). Offline; skipped until the evidence exists."""

from __future__ import annotations

import json
import pathlib

import pytest

from fusion_first.validate.llama_guard import parse_verdict, score

ROOT = pathlib.Path(__file__).resolve().parents[1]
V1 = ROOT / "evals/validation/v1"
EVIDENCE = V1 / "step2_guard.json"


def _jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.unit
@pytest.mark.skipif(not EVIDENCE.exists(), reason="step 2 has not been committed yet")
def test_the_committed_step2_result_re_derives_from_its_rows_and_raw_files():
    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    lg = {(r["config"], r["model"], r["item_id"]): parse_verdict(r["output"])["label"]
          for r in _jsonl(V1 / "step2/lg_raw.jsonl")}
    prior = {(r["model"], r["item_id"]): r["outcome"] for r in _jsonl(V1 / "step2/prior.jsonl")}
    rows = []
    for r in ev["rows"]:
        key = (r["model"], r["item_id"])
        assert (lg[("a", *key)], lg[("b", *key)]) == (r["lg_a"], r["lg_b"])
        old = prior[key]
        assert old["attack"] == r["attack"]
        assert r["prior"] == (bool(old["stopped"]) if old["attack"] else bool(old["blocked_any"]))
        rows.append({**r, ("stopped" if r["attack"] else "blocked_any"): r["fusion"]})
    again = score(rows)
    for key in ("fusion", "fusion_prior", "llama_guard_a", "llama_guard_b", "union_fusion_b", "comparisons",
                "by_attack_type"):
        assert again[key] == ev[key], key
    assert len(rows) == 400 and ev["guardrail_git_sha"].startswith("0c560b5")
    assert (ev["fusion"]["all"]["stopped"], ev["fusion"]["all"]["attacks"]) == (132, 148)
    assert ev["decision"] == {"new_rules": "adopted", "vs_prior": "fusion_better",
                              "vs_llama_guard_a": "fusion_better", "vs_llama_guard_b": "fusion_better"}
