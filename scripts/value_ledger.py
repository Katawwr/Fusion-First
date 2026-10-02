"""Build the value ledger from committed evidence (see fusion_first/validate/value_ledger.py).

    python scripts/value_ledger.py [--store DIR] --out evals/validation/v1/value_ledger.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.experiments import build_items  # noqa: E402
from fusion_first.validate.transcripts import STORE_DIR_DEFAULT, TranscriptStore  # noqa: E402
from fusion_first.validate.value_ledger import value_ledger  # noqa: E402

MODELS = ["llama3.2:1b", "qwen2.5:1.5b", "gemma3:1b", "qwen2.5:3b"]
GUARD = "evals/validation/v1/guard_on_transcripts.json"
FIX = "evals/validation/v1/evidence_oracle.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="value_ledger")
    p.add_argument("--store", default=str(ROOT / STORE_DIR_DEFAULT))
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    guard = json.loads((ROOT / GUARD).read_text(encoding="utf-8"))
    fix = json.loads((ROOT / FIX).read_text(encoding="utf-8"))
    items = {e: build_items(e, 30) for e in ("injecagent", "gandalf")}
    ledger = value_ledger(items, MODELS, TranscriptStore(a.store), guard)
    xs = fix["pooled"]["xstest"]["before_after"]
    ledger.update({
        "demonstration": False,
        "kind": "value ledger: what the prompt fix and the runtime guardrail each bought on real attacks",
        "generated_at": _dt.date.today().isoformat(),
        "sources": [GUARD, FIX, "evals/validation/v1/transcripts/ (v1 sample)"],
        "models": MODELS,
        "fix_refusal_cost": {"safe_requests_newly_refused": xs["discordant_c"],
                             "safe_requests_newly_answered": xs["discordant_b"], "pairs": xs["n_pairs"]},
        "note": "The guardrail was measured on the prompt as written, not behind the fix, so 'either' "
                "approximates running both layers.",
    })
    (ROOT / a.out).write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8", newline="\n")
    t = ledger["total"]
    print(f"found {t['found']}: fix removed {t['fix_removed']}, guard stopped {t['guard_stopped']}, "
          f"either {t['either']}, neither {t['neither']}; fix caused {t['fix_caused']} new attacks; "
          f"fix newly refused {xs['discordant_c']} safe requests (and newly answered {xs['discordant_b']})")
    for m, s in ledger["by_model"].items():
        print(f"  {m:13} found {s['found']:3}  fix {s['fix_removed']:3}  guard {s['guard_stopped']:3}  "
              f"either {s['either']:3}  neither {s['neither']:3}  fix-caused {s['fix_caused']:3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
