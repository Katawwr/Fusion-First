"""Llama Guard 3 8B as the detector study's comparator (dev-only; local Ollama only; no spend).

    python scripts/detector_lg3.py subsample [--n 200] [--seed 42] [--force]
    python scripts/detector_lg3.py probe [--n 5] [--arm configured] [--force]
    python scripts/detector_lg3.py run --arm configured|default [--n N] [--force]

PREREG_detector_v1.md (arm B2): Llama Guard 3 (`llama-guard3:8b`) on a stratified subsample of the CONFIRMATORY
rows, prompted in raw mode exactly as `scripts/guard_vs_llama_guard.py::ask` (POST /api/generate, raw, no stream,
temperature 0) with Meta's format: the request and the tool result in the User turn, the Agent turn empty, the last
User message assessed (`fusion_first.validate.llama_guard.tool_result_prompt`). Any "unsafe" first line is a
positive. `configured` adds S16 (prompt injection) to Meta's 14 categories; `default` is Meta's 14 and runs on the
first rows of the subsample (`--n`) if the timing probe leaves room.

- `subsample` verifies the seal, draws `--n` ids balanced over source x label (seeded; ids only) and writes
  evals/validation/v1/detector/lg3_subsample.json; it refuses to replace a different subsample without --force.
- `probe` times `--n` items of the subsample for one arm (outputs discarded) and prints seconds per item and the
  projected total for each arm.
- `run` appends one record per row to evals/validation/v1/detector/lg3_raw.jsonl ({id, arm, model_digest,
  prompt_sha256, output, verdict, seconds}) and skips rows already recorded for the arm, so it resumes.

`probe` and `run` refuse while Ollama has another model loaded (one Ollama job at a time) unless --force.
Relative paths resolve from the repository root.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate import detector_confirmatory as dc  # noqa: E402
from fusion_first.validate.llama_guard import MODEL, TOOL_RESULT_ARMS, parse_verdict  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 24}  # as scripts/guard_vs_llama_guard.py
N, SEED, PROBE_N, DEFAULT_ARM_N = 200, 42, 5, 100  # DEFAULT_ARM_N: the off-the-shelf arm's registered first rows
RETRIES = 3


def _path(p: str) -> pathlib.Path:
    path = pathlib.Path(p)
    return path if path.is_absolute() else ROOT / path


def http_transport(base: str = OLLAMA):
    """GET when `payload` is None, else POST JSON; returns the decoded reply."""
    def call(path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{base}{path}", data, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.load(resp)
    return call


def ask(transport, model: str, prompt: str) -> str:
    """Meta's prompt in raw mode, as scripts/guard_vs_llama_guard.py::ask sends it."""
    out = transport("/api/generate", {"model": model, "stream": False, "raw": True, "options": OPTIONS,
                                      "prompt": prompt})
    return out["response"]


def other_models(transport, model: str) -> list[str]:
    """Models `ollama ps` shows loaded, other than `model`."""
    loaded = transport("/api/ps", None).get("models", []) or []
    names = {m.get("name") or m.get("model") for m in loaded}
    return sorted(n for n in names if n and n not in (model, f"{model}:latest"))


def installed_digest(transport, model: str) -> str | None:
    for m in transport("/api/tags", None).get("models", []) or []:
        if m.get("name") in (model, f"{model}:latest"):
            return m.get("digest")
    return None


def _sealed(a) -> tuple[list[dict], str]:
    return dc.sealed_rows(_path(a.data), _path(a.seal))


def _subsample_doc(rows: list[dict], n: int, seed: int, digest: str) -> dict:
    ids = dc.stratified_subsample(rows, n, seed)
    by_id = {r["id"]: r for r in rows}
    strata: dict[str, int] = {}
    for i in ids:
        key = f"{by_id[i]['source']}:{by_id[i]['label']}"
        strata[key] = strata.get(key, 0) + 1
    return {"seed": seed, "n": n, "seal_digest": digest, "rule": dc.SUBSAMPLE_RULE,
            "strata": dict(sorted(strata.items())), "ids": ids}


def cmd_subsample(a) -> int:
    rows, digest = _sealed(a)
    doc = _subsample_doc(rows, a.n, a.seed, digest)
    out = _path(a.subsample)
    if out.is_file():
        prior = json.loads(out.read_text(encoding="utf-8"))
        if prior == doc:
            print(json.dumps({"subsample": str(out), "n": a.n, "unchanged": True}))
            return 0
        if not a.force:
            print(f"subsample: {out} already holds a different subsample (n={len(prior.get('ids', []))}); the "
                  "comparator's rows are fixed once (pass --force to replace it)", file=sys.stderr)
            return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"subsample": str(out), "n": a.n, "strata": doc["strata"]}))
    return 0


def _plan(a) -> tuple[list[dict], list[str]]:
    """The sealed rows and the subsample ids (the subsample must exist and match the seal)."""
    rows, digest = _sealed(a)
    by_id = {r["id"]: r for r in rows}
    return rows, dc.load_subsample(_path(a.subsample), by_id, digest)


def _ready(a, transport) -> str:
    """The installed model's digest, once Ollama is free for this job; raises RuntimeError otherwise."""
    others = other_models(transport, a.model)
    if others and not a.force:
        raise RuntimeError(f"Ollama has another model loaded ({', '.join(others)}): one Ollama job at a time "
                           "(stop it, or pass --force)")
    digest = installed_digest(transport, a.model)
    if not digest:
        raise RuntimeError(f"{a.model} is not installed in Ollama")
    return digest


def _timed(transport, model: str, prompt: str) -> tuple[str, float]:
    for attempt in range(1, RETRIES + 1):
        try:
            start = time.perf_counter()
            output = ask(transport, model, prompt)
            return output, time.perf_counter() - start
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as e:
            if attempt == RETRIES:
                raise RuntimeError(f"Llama Guard call failed {RETRIES} times: {e}") from e
            print(f"  retry {attempt}: {e}", file=sys.stderr, flush=True)
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def cmd_probe(a, transport) -> int:
    rows, ids = _plan(a)
    _ready(a, transport)
    by_id = {r["id"]: r for r in rows}
    seconds = []
    for rid in ids[:a.n]:
        _, s = _timed(transport, a.model, dc.lg3_prompt(by_id[rid], a.arm))
        seconds.append(round(s, 3))
        print(f"{rid}: {s:.1f} s", flush=True)
    per = statistics.median(seconds)
    projected = {"configured": per * len(ids), "default": per * min(DEFAULT_ARM_N, len(ids))}
    print(json.dumps({"arm": a.arm, "seconds": seconds, "seconds_per_item": per, "subsample": len(ids),
                      "projected_total_s": projected}))
    return 0


def _recorded(raw: pathlib.Path, arm: str) -> set[str]:
    if not raw.is_file():
        return set()
    recs = [json.loads(x) for x in raw.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["id"] for r in recs if r["arm"] == arm}


def cmd_run(a, transport) -> int:
    rows, ids = _plan(a)
    digest = _ready(a, transport)
    by_id = {r["id"]: r for r in rows}
    raw = _path(a.raw)
    done = _recorded(raw, a.arm)
    todo = [rid for rid in ids[:a.n] if rid not in done]
    raw.parent.mkdir(parents=True, exist_ok=True)
    for k, rid in enumerate(todo, 1):
        prompt = dc.lg3_prompt(by_id[rid], a.arm)
        output, seconds = _timed(transport, a.model, prompt)
        rec = {"id": rid, "arm": a.arm, "model_digest": digest, "prompt_sha256": dc.prompt_sha256(prompt),
               "output": output, "verdict": parse_verdict(output)["label"], "seconds": round(seconds, 3)}
        with raw.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{k}/{len(todo)} {a.arm} {rid}: {rec['verdict']} ({seconds:.1f} s)", flush=True)
    print(json.dumps({"arm": a.arm, "raw": str(raw), "new": len(todo), "recorded": len(done) + len(todo)}))
    return 0


def main(argv: list[str] | None = None, *, transport=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", default=dc.DATA)
    common.add_argument("--seal", default=dc.SEAL)
    common.add_argument("--subsample", default=dc.SUBSAMPLE)
    common.add_argument("--raw", default=dc.LG3_RAW)
    common.add_argument("--model", default=MODEL)
    common.add_argument("--ollama", default=OLLAMA)
    common.add_argument("--force", action="store_true",
                        help="subsample: replace a different subsample; probe/run: ignore other loaded models")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("subsample", parents=[common], help="draw the stratified confirmatory subsample (ids only)")
    s.add_argument("--n", type=int, default=N)
    s.add_argument("--seed", type=int, default=SEED)
    p = sub.add_parser("probe", parents=[common], help="time a few items and project the run")
    p.add_argument("--n", type=int, default=PROBE_N)
    p.add_argument("--arm", choices=TOOL_RESULT_ARMS, default="configured")
    r = sub.add_parser("run", parents=[common], help="record Llama Guard's replies (resumable)")
    r.add_argument("--arm", choices=TOOL_RESULT_ARMS, required=True)
    r.add_argument("--n", type=int, default=None, help="the first N subsample rows (default: all)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "subsample":
            return cmd_subsample(a)
        transport = transport or http_transport(a.ollama)
        return cmd_probe(a, transport) if a.cmd == "probe" else cmd_run(a, transport)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"{a.cmd}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
