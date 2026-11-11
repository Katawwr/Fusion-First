"""Content safety, Llama Guard 3's own job: Llama Guard 3 (off the shelf) and Fusion's guard on harmful and benign
prompts. Pre-registered in evals/validation/v1/PREREG_content_safety.md. Dev-only; local Ollama only; no spend.

    python scripts/content_safety.py plan          # the prompts and the size of the one Ollama job
    python scripts/content_safety.py seal          # write the seal (before the registration commit)
    python scripts/content_safety.py llama-guard   # Llama Guard 3's verdicts; resumable; ONE Ollama job
    python scripts/content_safety.py score         # verifies the seal and every record; writes the evidence once

`llama-guard` sends each prompt in Meta's format with the 14 default categories, one User turn, the User message
assessed (`fusion_first.validate.llama_guard.user_prompt`), raw mode, temperature 0, exactly as
`scripts/detector_lg3.py`; it refuses any model but the registered one and refuses while Ollama has another model
loaded. Fusion's guard is deterministic and runs inside `score`.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import hashlib
import importlib.util
import json
import pathlib
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate import guard_compare as gc  # noqa: E402
from fusion_first.validate.llama_guard import MODEL as LG_MODEL  # noqa: E402
from fusion_first.validate.llama_guard import parse_verdict, user_prompt  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    seal_digest,
    verify_seal,
    write_seal,
)

# Registered (PREREG_content_safety.md); changing any of these after registration voids the run.
GUARD_SHA = "5a89479ca515c5bdf04164b98eaaf80b8639f881"  # the published rules: last commit to fusion_first/guardrail
RULE_PATHS = ("fusion_first/guardrail",)
PINNED = (*RULE_PATHS, "datasets/external/xstest.v1.jsonl", "datasets/external/jbb.v1.jsonl",
          "scripts/content_safety.py", "fusion_first/validate/guard_compare.py",
          "fusion_first/validate/llama_guard.py", "fusion_first/validate/prereg.py")
PREREG = "evals/validation/v1/PREREG_content_safety.md"
DIR = ROOT / "evals/validation/v1/content_safety"
SEAL = DIR / "prompts.seal.json"
RAW = DIR / "lg_raw.jsonl"
OUT = ROOT / "evals/validation/v1/content_safety.json"
SECONDS_PER_PROMPT = 7.4  # Llama Guard 3 8B on this machine, from the detector study's committed latencies


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _lg3():
    """scripts/detector_lg3.py: the Ollama transport, the one-job-at-a-time check and the retrying call."""
    spec = importlib.util.spec_from_file_location("detector_lg3", ROOT / "scripts" / "detector_lg3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def rows() -> list[dict]:
    """The registered prompts, each with the hash of the exact Llama Guard prompt it is sent in."""
    return [{**r, "lg_prompt_sha256": prompt_sha256(user_prompt(r["prompt"]))} for r in gc.content_rows()]


def sealed_rows() -> tuple[list[dict], str]:
    """(the prompts, the seal's digest), only when they match the seal exactly."""
    if not SEAL.is_file():
        raise SystemExit(f"no seal at {_rel(SEAL)}: run `seal` and commit it with the registration first")
    seal = load_seal(SEAL)
    rs = rows()
    drift = verify_seal(rs, seal)
    if any(drift.values()):
        raise SystemExit(f"the prompts do not match their seal: { {k: v[:3] for k, v in drift.items() if v} }")
    return rs, seal_digest(seal)


def verdicts(rs: list[dict], records: list[dict]) -> dict[str, dict]:
    """{prompt id: its Llama Guard record}. Refuses a duplicate, a record made from another prompt, by another model
    or by more than one set of weights, a stored verdict its output does not give, and a prompt with no record."""
    by_id = {r["id"]: r for r in rs}
    out: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("id")
        if rid not in by_id:
            raise ValueError(f"{rid}: a record for a prompt that is not registered")
        if rid in out:
            raise ValueError(f"{rid}: recorded twice")
        if rec.get("lg_model") != LG_MODEL:
            raise ValueError(f"{rid}: recorded by {rec.get('lg_model')!r}, not the registered {LG_MODEL!r}")
        if rec.get("prompt_sha256") != by_id[rid]["lg_prompt_sha256"]:
            raise ValueError(f"{rid}: the recorded prompt is not the registered one")
        if rec.get("verdict") != parse_verdict(rec.get("output"))["label"]:
            raise ValueError(f"{rid}: the stored verdict does not follow from the output")
        out[rid] = rec
    missing = [r["id"] for r in rs if r["id"] not in out]
    if missing:
        raise ValueError(f"no Llama Guard record for {len(missing)} prompt(s), first {missing[0]}")
    digests = {rec.get("model_digest") for rec in out.values()}
    if len(digests) != 1 or None in digests:
        raise ValueError(f"the records name {len(digests)} model digests; one set of weights is registered")
    return out


def scored_rows(rs: list[dict], by_id: dict[str, dict]) -> list[dict]:
    """One row per prompt as both systems judged it. An unparseable Llama Guard reply flags nothing."""
    out = []
    for r in rs:
        rec, guard = by_id[r["id"]], gc.guard_prompt_flag(r["prompt"])
        parsed = parse_verdict(rec["output"])
        out.append({"id": r["id"], "source": r["source"], "label": r["label"], "llama_guard": parsed["label"],
                    "llama_guard_categories": parsed["categories"], "fusion_input": guard["input"],
                    "fusion_output": guard["output"],
                    "systems": {"llama_guard": parsed["label"] == "unsafe", "fusion": guard["flagged"]}})
    return out


# ------------------------------------------------------------------------------------------------ commands
def cmd_plan() -> int:
    rs = rows()
    counts = collections.Counter((r["source"], r["label"]) for r in rs)
    done = {r["id"] for r in _jsonl(RAW)}
    todo = sum(r["id"] not in done for r in rs)
    print(json.dumps({"prompts": len(rs), "by_source_and_label": {f"{s}:{label}": n for (s, label), n in
                                                                  sorted(counts.items())},
                      "sealed": SEAL.is_file(), "llama_guard_recorded": len(rs) - todo, "llama_guard_to_run": todo,
                      "projected_minutes": round(todo * SECONDS_PER_PROMPT / 60), "scored": OUT.is_file()}, indent=1))
    return 0


def cmd_seal() -> int:
    if SEAL.exists():
        raise SystemExit(f"{_rel(SEAL)} exists: the prompts are sealed once")
    rs = rows()
    counts = collections.Counter(f"{r['source']}:{r['label']}" for r in rs)
    write_seal(SEAL, compute_seal(rs), meta={
        "study": "content safety: Llama Guard 3 off the shelf vs Fusion's guard", "rows": dict(sorted(counts.items())),
        "llama_guard_model": LG_MODEL, "guardrail_git_sha": GUARD_SHA})
    print(json.dumps({"seal": _rel(SEAL), "rows": len(rs)}))
    return 0


def cmd_llama_guard(model: str, force: bool, ollama: str | None, transport=None) -> int:
    if model != LG_MODEL:
        raise SystemExit(f"--model {model!r} is refused: the registered model is {LG_MODEL!r}")
    rs, _ = sealed_rows()
    lg3 = _lg3()
    transport = transport or lg3.http_transport(ollama or lg3.OLLAMA)
    others = lg3.other_models(transport, model)
    if others and not force:
        raise SystemExit(f"Ollama has another model loaded ({', '.join(others)}): one Ollama job at a time")
    digest = lg3.installed_digest(transport, model)
    if not digest:
        raise SystemExit(f"{model} is not installed in Ollama")
    done = {r["id"] for r in _jsonl(RAW)}
    todo = [r for r in rs if r["id"] not in done]
    DIR.mkdir(parents=True, exist_ok=True)
    for k, r in enumerate(todo, 1):
        prompt = user_prompt(r["prompt"])
        output, seconds = lg3._timed(transport, model, prompt)
        rec = {"id": r["id"], "lg_model": model, "model_digest": digest, "prompt_sha256": prompt_sha256(prompt),
               "output": output, "verdict": parse_verdict(output)["label"], "seconds": round(seconds, 3)}
        with RAW.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{k}/{len(todo)} {r['id']}: {rec['verdict']} ({seconds:.1f} s)", flush=True)
    print(json.dumps({"raw": _rel(RAW), "new": len(todo), "recorded": len(done) + len(todo)}))
    return 0


def evidence(rs: list[dict], records: list[dict], *, digest: str) -> dict:
    """The evidence document from the sealed prompts and the raw records (no git, no clock: `cmd_score` adds them)."""
    by_id = verdicts(rs, records)
    scored = scored_rows(rs, by_id)
    seconds = [rec["seconds"] for rec in by_id.values() if isinstance(rec.get("seconds"), int | float)]
    return {
        "demonstration": False,
        "kind": "content safety: Llama Guard 3 off the shelf vs Fusion's runtime guard on harmful and benign prompts",
        "preregistration": PREREG,
        "llama_guard": {"model": LG_MODEL, "digest": next(iter(by_id.values()))["model_digest"],
                        "prompt": "Meta's format, the 14 default categories, one User turn, the User message assessed",
                        "unparseable": sum(r["llama_guard"] == "unparseable" for r in scored),
                        "median_seconds": round(statistics.median(seconds), 3) if seconds else None},
        "fusion": {"configuration": "default GuardConfig; flagged when guard_input (untrusted) or guard_output "
                                    "does not allow"},
        "seal": {"path": _rel(SEAL), "n_rows": len(rs), "digest": digest},
        **gc.score_content_safety(scored),
        "rows": [{k: v for k, v in r.items() if k != "systems"} | {"fusion": r["systems"]["fusion"]} for r in scored],
    }


def cmd_score() -> int:
    if OUT.exists():
        raise SystemExit(f"{_rel(OUT)} exists: the sealed prompts are scored once")
    if _git("status", "--porcelain", "--", *PINNED, _rel(SEAL), _rel(RAW)):
        raise SystemExit("the rules, the prompts, the seal, the raw records or the scorer are modified in the working "
                         "tree: commit them first")
    rules = _git("log", "-1", "--format=%H", "--", *RULE_PATHS)
    if rules != GUARD_SHA:
        raise SystemExit(f"{RULE_PATHS} are at {rules}, not the registered {GUARD_SHA}")
    rs, digest = sealed_rows()
    try:
        doc = evidence(rs, _jsonl(RAW), digest=digest)
    except ValueError as exc:
        raise SystemExit(f"score: {exc}") from exc
    doc = {**{k: doc[k] for k in ("demonstration", "kind", "preregistration")},
           "measured": _dt.date.today().isoformat(), "git_sha": _git("rev-parse", "HEAD"),
           "guardrail_git_sha": rules, **{k: v for k, v in doc.items()
                                          if k not in ("demonstration", "kind", "preregistration")}}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for label in ("unsafe", "safe"):
        s = doc[label]["systems"]
        print(f"{label:6} n={doc[label]['n']}: Llama Guard 3 flagged {s['llama_guard']['k']}, "
              f"Fusion's guard flagged {s['fusion']['k']}")
    print(f"decision: {doc['decision']['verdict']} ({doc['decision']['reason']})")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="content_safety", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("seal")
    lg = sub.add_parser("llama-guard")
    lg.add_argument("--model", default=LG_MODEL)
    lg.add_argument("--ollama", default=None)
    lg.add_argument("--force", action="store_true", help="run although Ollama has another model loaded")
    sub.add_parser("score")
    a = p.parse_args(argv)
    if a.cmd == "plan":
        return cmd_plan()
    if a.cmd == "seal":
        return cmd_seal()
    if a.cmd == "llama-guard":
        return cmd_llama_guard(a.model, a.force, a.ollama)
    return cmd_score()


if __name__ == "__main__":
    raise SystemExit(main())
