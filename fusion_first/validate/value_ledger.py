"""The value ledger: what the prompt fix and the guard each bought on real attacks (committed evidence).

`guard_stopped` is read from the registered per-item guard results, never recomputed. The guard was
measured on the prompt as written, so "either" only approximates running both layers.
"""

from __future__ import annotations

from fusion_first.stats.metrics import wilson_interval
from fusion_first.validate.analysis import paired_labels
from fusion_first.validate.experiments import ARMS, EvidenceItem
from fusion_first.validate.transcripts import TranscriptStore

_COUNTS = ("found", "fix_removed", "guard_stopped", "either", "neither", "fix_caused")


def _rate(k: int, n: int) -> dict:
    iv = wilson_interval(k, n)
    return {"point": round(iv.point, 4), "low": round(iv.low, 4), "high": round(iv.high, 4), "k": k, "n": n}


def _tally(rows: list[dict]) -> dict:
    t = {k: sum(1 for r in rows if r[k]) for k in _COUNTS}
    for k in ("fix_removed", "guard_stopped", "either", "neither"):
        t[f"{k}_rate"] = _rate(t[k], t["found"])
    return t


def value_ledger(items_by_exp: dict[str, list[EvidenceItem]], models: list[str], store: TranscriptStore,
                 guard_evidence: dict) -> dict:
    not_stopped = set(guard_evidence.get("not_stopped", []))
    rows = []
    for exp, items in items_by_exp.items():
        for model in models:
            recs = store.load(exp, model)
            for item in items:
                status, labels = paired_labels(item, recs, ARMS)
                if status != "ok":
                    continue
                found, with_fix = labels[0].is_issue, labels[1].is_issue
                fix_removed = found and not with_fix
                guard_stopped = found and f"{model} {item.item_id}" not in not_stopped
                rows.append({"model": model, "experiment": exp, "found": found, "fix_removed": fix_removed,
                             "guard_stopped": guard_stopped, "either": fix_removed or guard_stopped,
                             "neither": found and not (fix_removed or guard_stopped),
                             "fix_caused": (not found) and with_fix})
    total = _tally(rows)
    recorded = guard_evidence.get("all", {}).get("attacks")
    if recorded is not None and recorded != total["found"]:
        raise ValueError(f"the guard measurement covers {recorded} attacks but the transcripts show "
                         f"{total['found']} found: they are not the same attacks")
    return {
        "total": total,
        "by_model": {m: _tally([r for r in rows if r["model"] == m]) for m in models},
        "by_experiment": {e: _tally([r for r in rows if r["experiment"] == e]) for e in items_by_exp},
        "guard_over_block": {"over_blocked": guard_evidence.get("all", {}).get("over_blocked"),
                             "clean": guard_evidence.get("all", {}).get("clean")},
    }
