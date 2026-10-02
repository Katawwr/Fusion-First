"""Time a few local generations to budget an evidence run (outputs discarded; items from the spent v1 sample).

    python scripts/time_generations.py --model qwen2.5:7b --num-ctx 8192,4096 [--k 1] [--out <scratch>.json]

Same request shape as the evidence runner: temperature 0, seed 7, the safety cap.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate.experiments import build_items  # noqa: E402

BASE = "http://127.0.0.1:11434"
EXPERIMENTS = ("injecagent", "gandalf", "xstest")


def _post(path: str, payload: dict | None, timeout: float = 1800) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _gpu_share(model: str) -> float | None:
    for m in _post("/api/ps", None).get("models", []):
        if m.get("name") == model or m.get("model") == model:
            return round(m["size_vram"] / m["size"], 3) if m.get("size") else None
    return None


def time_one(model: str, num_ctx: int, system: str, user: str, cap: int) -> dict:
    r = _post("/api/chat", {
        "model": model, "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0.0, "seed": 7, "num_predict": cap, "num_ctx": num_ctx},
    })
    s = 1e-9
    return {"load_s": round(r.get("load_duration", 0) * s, 2),
            "prompt_tokens": r.get("prompt_eval_count", 0), "prompt_s": round(r.get("prompt_eval_duration", 0) * s, 2),
            "gen_tokens": r.get("eval_count", 0), "gen_s": round(r.get("eval_duration", 0) * s, 2),
            "total_s": round(r.get("total_duration", 0) * s, 2)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="time_generations")
    p.add_argument("--model", required=True)
    p.add_argument("--num-ctx", default="8192,4096")
    p.add_argument("--k", type=int, default=1, help="items per experiment (each timed in both arms)")
    p.add_argument("--cap", type=int, default=256)
    p.add_argument("--out")
    a = p.parse_args(argv)
    rows = []
    for num_ctx in (int(x) for x in a.num_ctx.split(",")):
        _post("/api/generate", {"model": a.model, "keep_alive": 0})  # unload: the next call loads at this num_ctx
        share = None
        for exp in EXPERIMENTS:
            for it in build_items(exp, a.k):
                for arm in ("baseline", "hardened"):
                    t = time_one(a.model, num_ctx, it.system_for(arm), it.user, a.cap)
                    share = share if share is not None else _gpu_share(a.model)
                    rows.append({"num_ctx": num_ctx, "experiment": exp, "arm": arm, "item": it.item_id, **t})
                    print(json.dumps(rows[-1]), flush=True)
        for r in rows:
            if r["num_ctx"] == num_ctx:
                r["gpu_share"] = share
    print("\nnum_ctx  gpu_share  median s/generation (excl. load)  gen tok/s  prompt tok/s")
    for num_ctx in sorted({r["num_ctx"] for r in rows}):
        rs = [r for r in rows if r["num_ctx"] == num_ctx]
        per = statistics.median(r["total_s"] - r["load_s"] for r in rs)
        gen = sum(r["gen_tokens"] for r in rs) / max(sum(r["gen_s"] for r in rs), 1e-9)
        pr = sum(r["prompt_tokens"] for r in rs) / max(sum(r["prompt_s"] for r in rs), 1e-9)
        print(f"{num_ctx:7}  {rs[0].get('gpu_share')!s:9}  {per:31.1f}  {gen:9.1f}  {pr:12.1f}")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
