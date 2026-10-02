"""Development readout for the runtime guard's tool-call rules: a diagnostic on spent InjecAgent samples and
the benign-actions `dev` cases, never evidence.

    python scripts/guard_dev.py [--harness v2|v3] [--out <scratch>/guard_dev.json] [--verbose]

The benign-actions `heldout` cases are sealed for a pre-registered run and cannot be selected here.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.benign_actions import (  # noqa: E402
    build_cases,
    dev_attacker_tools,
    evaluate,
    split_of,
)
from fusion_first.validate.experiments import SPENT, build_items  # noqa: E402
from fusion_first.validate.guard_on_transcripts import (  # noqa: E402
    HARNESSES,
    _calls,
    injecagent_outcome,
)
from fusion_first.validate.transcripts import STORE_DIR_DEFAULT, TranscriptStore  # noqa: E402

MODELS = ("llama3.2:1b", "qwen2.5:1.5b", "gemma3:1b", "qwen2.5:3b")
SAMPLE_NAMES = ("v1", "compact")
# Step 2's (spent) sample and models.
STEP2 = ("step2", ("fusion-evidence-step2-v1", 100, SPENT), ("qwen2.5:7b", "llama3.1:8b"))


def _samples(n: int):
    for name, spec in zip(SAMPLE_NAMES, SPENT, strict=True):
        yield name, build_items("injecagent", n, salt=spec[0], exclude=spec[2] if len(spec) > 2 else None), MODELS
    name, (salt, size, exclude), models = STEP2
    yield name, build_items("injecagent", size, salt=salt, exclude=exclude), models


def transcripts(n: int, harness: str = "v2") -> dict:
    store = TranscriptStore(ROOT / STORE_DIR_DEFAULT)
    table = defaultdict(lambda: {"attacks": 0, "stopped": 0, "clean": 0, "over_blocked": 0})
    misses, over = [], []
    for name, items, models in _samples(n):
        for model in models:
            recs = store.load("injecagent", model)
            for it in items:
                rec = recs.get((it.item_id, "baseline"))
                if rec is None or rec.error or rec.response is None:
                    continue
                o = injecagent_outcome(it, rec.response, harness=harness)
                row = table[f"{name}:{it.item_id.split(':')[1]}"]
                if o["attack"]:
                    row["attacks"] += 1
                    row["stopped"] += bool(o["stopped"])
                    if not o["stopped"]:
                        misses.append(f"{name} {model} {it.item_id} {[c for c, _ in _calls(rec.response, set())]}")
                else:
                    row["clean"] += 1
                    row["over_blocked"] += o["blocked_any"]
                    if o["blocked_any"]:
                        over.append(f"{name} {model} {it.item_id} {[c for c, _ in _calls(rec.response, set())]}")
    return {"by_sample_kind": dict(table), "not_stopped": misses, "over_blocked": over}


def benign() -> dict:
    dev = dev_attacker_tools()
    rows = [evaluate(c) for c in build_cases() if split_of(c, dev) == "dev"]
    by = defaultdict(lambda: {"cases": 0, "blocked": 0})
    rules = defaultdict(int)
    for r in rows:
        by[r["kind"]]["cases"] += 1
        by[r["kind"]]["blocked"] += r["blocked"]
        for b in r["blocked_calls"]:
            for rule in b["rules"]:
                rules[rule] += 1
    return {"by_kind": dict(by), "blocked_calls_by_rule": dict(rules),
            "blocked": [r for r in rows if r["blocked"]]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guard_dev")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--out", help="write the full readout (JSON) here, e.g. under the scratchpad")
    p.add_argument("--harness", choices=sorted(HARNESSES), default="v2")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args(argv)
    t, b = transcripts(a.n, a.harness), benign()
    print(f"DIAGNOSTIC (spent samples, harness {HARNESSES[a.harness]})")
    for g, s in sorted(t["by_sample_kind"].items()):
        print(f"  {g:12} attacks stopped {s['stopped']:3}/{s['attacks']:<3}  clean wrongly blocked "
              f"{s['over_blocked']:3}/{s['clean']}")
    print("  benign dev: " + ", ".join(f"{k} {v['blocked']}/{v['cases']} blocked" for k, v in sorted(b["by_kind"].items()))
          + f"  (blocked calls by rule: {dict(sorted(b['blocked_calls_by_rule'].items()))})")
    if a.verbose:
        for line in t["not_stopped"]:
            print("  miss  ", line)
        for line in t["over_blocked"]:
            print("  over  ", line)
        for r in b["blocked"]:
            print("  benign", r["case_id"], [(c["tool"], c["rules"]) for c in r["blocked_calls"]])
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps({"harness": HARNESSES[a.harness], "transcripts": t, "benign_dev": b}, indent=1),
                                       encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
