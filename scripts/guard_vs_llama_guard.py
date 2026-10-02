"""Fusion's runtime guardrail vs Llama Guard 3 on the fresh attack transcripts, pre-registered in
evals/validation/v1/PREREG_guard_vs_llama_guard.md.

    python scripts/guard_vs_llama_guard.py --out evals/validation/v1/guard_vs_llama_guard.json
    python scripts/guard_vs_llama_guard.py --offline --out ...   # re-derive from the committed verdicts

Resumable: every Llama Guard verdict is appended to evals/validation/v1/guard_vs_llama_guard/raw.jsonl
(commit it; --offline rebuilds the result from it without a model). Local Ollama only; no spend.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.experiments import build_items  # noqa: E402
from fusion_first.validate.guard_on_transcripts import (  # noqa: E402
    gandalf_outcome,
    injecagent_outcome,
)
from fusion_first.validate.llama_guard import (  # noqa: E402
    MODEL,
    configured_prompt,
    default_prompt,
    parse_verdict,
    score,
)
from fusion_first.validate.transcripts import STORE_DIR_DEFAULT, TranscriptStore  # noqa: E402

MODELS = ("llama3.2:1b", "qwen2.5:1.5b", "gemma3:1b", "qwen2.5:3b")
SALT, EXCLUDE = "fusion-evidence-compact-v1", ("fusion-evidence-v1", 30)
OUTCOME = {"injecagent": injecagent_outcome, "gandalf": gandalf_outcome}
PREREG = "evals/validation/v1/PREREG_guard_vs_llama_guard.md"
FRESH = "evals/validation/v1/guard_on_fresh_transcripts.json"
RAW = ROOT / "evals/validation/v1/guard_vs_llama_guard/raw.jsonl"
OLLAMA = "http://127.0.0.1:11434"
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 24}


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(f"{OLLAMA}{path}", json.dumps(payload).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.load(resp)


def ask(config: str, item, response: str, model: str) -> str:
    """Meta's prompt format in raw mode: A with the default categories, B with S15/S16 added."""
    prompt = default_prompt(item, response) if config == "a" else configured_prompt(item, response)
    out = _post("/api/generate", {"model": model, "stream": False, "raw": True, "options": OPTIONS,
                                  "prompt": prompt})
    return out["response"]


def transcripts() -> list[dict]:
    store = TranscriptStore(ROOT / STORE_DIR_DEFAULT)
    rows = []
    for exp, outcome in OUTCOME.items():
        for item in build_items(exp, 30, salt=SALT, exclude=EXCLUDE):
            for model in MODELS:
                rec = store.load(exp, model).get((item.item_id, "baseline"))
                if rec is None or rec.error or rec.response is None:
                    raise SystemExit(f"missing transcript: {exp} {model} {item.item_id}")
                kind = item.item_id.split(":")[1] if exp == "injecagent" else "leak"
                rows.append({"experiment": exp, "model": model, "item_id": item.item_id, "kind": kind,
                             **outcome(item, rec.response), "_item": item, "_response": rec.response})
    return rows


def _load_raw() -> dict:
    out = {}
    if RAW.exists():
        for line in RAW.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r["config"], r["model"], r["item_id"])] = r
    return out


def collect(rows: list[dict], model: str, offline: bool) -> dict:
    raw = _load_raw()
    todo = [(cfg, r) for cfg in ("a", "b") for r in rows if (cfg, r["model"], r["item_id"]) not in raw]
    if todo and offline:
        raise SystemExit(f"--offline: {len(todo)} verdicts missing from {RAW}")
    RAW.parent.mkdir(parents=True, exist_ok=True)
    for i, (cfg, r) in enumerate(todo, 1):
        for attempt in range(1, 100):  # registered: retry until every transcript has a verdict
            try:
                text = ask(cfg, r["_item"], r["_response"], model)
                break
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as e:
                print(f"  retry {attempt}: {cfg} {r['model']} {r['item_id']}: {e}", flush=True)
                time.sleep(min(60, 5 * attempt))
        entry = {"config": cfg, "model": r["model"], "item_id": r["item_id"], "lg_model": model, "output": text}
        with RAW.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry) + "\n")
        raw[(cfg, r["model"], r["item_id"])] = entry
        print(f"{i}/{len(todo)} {cfg} {r['model']} {r['item_id']}: {parse_verdict(text)['label']}", flush=True)
    return raw


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guard_vs_llama_guard")
    p.add_argument("--model", default=MODEL)
    p.add_argument("--offline", action="store_true", help="re-derive from the committed verdicts only")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    rows = transcripts()
    committed = json.loads((ROOT / FRESH).read_text(encoding="utf-8"))["all"]
    fusion = score([{**r, "lg_a": "safe", "lg_b": "safe"} for r in rows])["fusion"]["all"]
    same = (fusion["attacks"], fusion["stopped"], fusion["clean"], fusion["blocked"]) == \
           (committed["attacks"], committed["stopped"], committed["clean"], committed["over_blocked"])
    if not same:
        raise SystemExit(f"Fusion's recomputed outcomes {fusion} differ from the committed {committed}")

    raw = collect(rows, a.model, a.offline)
    for r in rows:
        for cfg in ("a", "b"):
            r[f"lg_{cfg}"] = parse_verdict(raw[(cfg, r["model"], r["item_id"])]["output"])["label"]
    public = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    digest = ""
    if not a.offline:
        from fusion_first.model.providers.ollama import model_digest

        digest = model_digest(a.model)
    evidence = {
        "demonstration": False,
        "kind": "runtime guardrail vs Llama Guard 3 on real small-model attack transcripts (oracle-labelled)",
        "preregistration": PREREG,
        "measured": _dt.date.today().isoformat(),
        "git_sha": _git("rev-parse", "HEAD"),
        "guardrail_git_sha": _git("log", "-1", "--format=%H", "--", "fusion_first/guardrail"),
        "llama_guard": {"model": a.model, "digest": digest,
                        "configs": {"a": "Meta's prompt format, default categories (raw mode)",
                                    "b": "Meta's prompt format + S15 (with the planted secret) + S16"}},
        "sample": {"salt": SALT, "exclude_salt": EXCLUDE[0]},
        "models": list(MODELS),
        "raw_verdicts": str(RAW.relative_to(ROOT)).replace("\\", "/"),
        **score(public),
        "rows": [{k: r[k] for k in ("experiment", "model", "item_id", "kind", "attack", "lg_a", "lg_b")}
                 | {"fusion": bool(r["stopped"]) if r["attack"] else bool(r["blocked_any"])} for r in public],
    }
    out = ROOT / a.out
    out.write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8", newline="\n")
    for s in ("fusion", "llama_guard_a", "llama_guard_b", "union_fusion_b"):
        x = evidence[s]["all"]
        print(f"{s:16} stopped {x['stopped']:3}/{x['attacks']} ({x['recall']['point']:.0%})   "
              f"wrongly blocked {x['blocked']:3}/{x['clean']} ({x['over_block']['point']:.0%})")
    for name, c in evidence["comparisons"].items():
        print(f"{name}: {c['decision']}  attacks p={c['attacks']['mcnemar_p']:.4f}  clean p={c['clean']['mcnemar_p']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
