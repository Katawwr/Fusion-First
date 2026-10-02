"""Apply the runtime guardrail to the real attack transcripts of the v1 evidence run (pre-registered in
evals/validation/v1/PREREG_guard_on_real_transcripts.md) and write the evidence file.

    python scripts/guard_on_transcripts.py [--store DIR] --out evals/validation/v1/guard_on_transcripts.json

Offline: committed transcripts, the production Guardrail, and the deterministic oracles.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.experiments import build_items  # noqa: E402
from fusion_first.validate.guard_on_transcripts import (  # noqa: E402
    gandalf_outcome,
    injecagent_outcome,
    summarize,
)
from fusion_first.validate.transcripts import STORE_DIR_DEFAULT, TranscriptStore  # noqa: E402

MODELS = ("llama3.2:1b", "qwen2.5:1.5b", "gemma3:1b", "qwen2.5:3b")
OUTCOME = {"injecagent": injecagent_outcome, "gandalf": gandalf_outcome}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guard_on_transcripts")
    p.add_argument("--store", default=str(ROOT / STORE_DIR_DEFAULT))
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--salt", default="fusion-evidence-v1", help="item sample salt")
    p.add_argument("--exclude-salt", default=None, help="drop every item of this other sample (same --n)")
    p.add_argument("--preregistration", default="evals/validation/v1/PREREG_guard_on_real_transcripts.md")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    store = TranscriptStore(a.store)
    rows, missing = [], 0
    for exp, outcome in OUTCOME.items():
        exclude = (a.exclude_salt, a.n) if a.exclude_salt else None
        items = build_items(exp, a.n, salt=a.salt, exclude=exclude)
        for model in MODELS:
            recs = store.load(exp, model)
            for item in items:
                rec = recs.get((item.item_id, "baseline"))
                if rec is None or rec.error or rec.response is None:
                    missing += 1
                    continue
                o = outcome(item, rec.response)
                kind = item.item_id.split(":")[1] if exp == "injecagent" else "leak"
                rows.append({"experiment": exp, "model": model, "item_id": item.item_id, "kind": kind, **o})

    def grouped(key) -> dict:
        return summarize([{**r, "group": key(r)} for r in rows])

    sha = subprocess.run(["git", "log", "-1", "--format=%H", "--", "fusion_first/guardrail"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    evidence = {
        "demonstration": False,
        "kind": "runtime guardrail applied to real small-model attack transcripts (oracle-labelled)",
        "preregistration": a.preregistration,
        "sample": {"salt": a.salt, "exclude_salt": a.exclude_salt},
        "measured": _dt.date.today().isoformat(),
        "guardrail_git_sha": sha,
        "arm": "baseline",
        "models": list(MODELS),
        "n_per_experiment": a.n,
        "missing_transcripts": missing,
        "all": summarize([{**r, "group": "all"} for r in rows])["all"],
        "by_experiment": grouped(lambda r: r["experiment"]),
        "by_attack_type": grouped(lambda r: f"{r['experiment']}:{r['kind']}"),
        "by_model": grouped(lambda r: f"{r['experiment']}/{r['model']}"),
        "not_stopped": [f"{r['model']} {r['item_id']}" for r in rows if r["attack"] and not r["stopped"]],
        "over_blocked": [f"{r['model']} {r['item_id']}" for r in rows if not r["attack"] and r["blocked_any"]],
    }
    out = ROOT / a.out
    out.write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8", newline="\n")
    for g, s in evidence["by_attack_type"].items():
        print(f"{g:18} attacks {s['attacks']:3} stopped {s['stopped']:3} ({s['recall']['point']:.0%})   "
              f"clean {s['clean']:3} over-blocked {s['over_blocked']:3} ({s['over_block']['point']:.0%})")
    s = evidence["all"]
    print(f"{'ALL':18} attacks {s['attacks']:3} stopped {s['stopped']:3} ({s['recall']['point']:.0%})   "
          f"clean {s['clean']:3} over-blocked {s['over_blocked']:3} ({s['over_block']['point']:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
