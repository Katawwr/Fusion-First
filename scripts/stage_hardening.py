"""Does the content-safety stage's own handling change outcomes? Llama Guard 3 asked raw (the text in Meta's
template as it is) and through the shipped stage, on held-back OR-Bench prompts in fixed attack and benign forms
(`fusion_first/validate/stage_hardening.py`). To be pre-registered in
evals/validation/v1/PREREG_stage_hardening.md. Dev-only; local Ollama only; no spend.

    python scripts/stage_hardening.py plan               # where every step stands; the size of each Ollama job
    python scripts/stage_hardening.py pilot [--n 20]     # development: the forms on seen JBB prompts, both arms
    python scripts/stage_hardening.py seal               # write the seal (before the registration commit)
    python scripts/stage_hardening.py classify           # Llama Guard's replies to every sealed prompt (resumable)
    python scripts/stage_hardening.py score              # verifies the seal and every record; writes once

`pilot` and `classify` are ONE Ollama job each: they refuse any model but the registered one and refuse while Ollama
has another model loaded. Every reply is recorded under the sha256 of the exact prompt sent; `score` replays the
replies through the shipped guard and stage, so the flags are the shipped code's.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import pathlib
import statistics
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.guardrail.stages import LLAMA_GUARD_MODEL, LlamaGuard, parse_verdict  # noqa: E402
from fusion_first.validate import experiments  # noqa: E402
from fusion_first.validate import stage_hardening as sh  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    load_seal_meta,
    seal_digest,
    verify_seal,
    write_seal,
)

# Everything a flag or a statistic depends on. `seal` records each path's git object id; `classify` and `score`
# refuse a tree in which any of them differs.
PINNED = ("fusion_first/guardrail", "fusion_first/security", "fusion_first/stats", "fusion_first/offline.py",
          "fusion_first/validate/stage_hardening.py", "fusion_first/validate/guard_compare.py",
          "fusion_first/validate/seal.py", "fusion_first/validate/experiments.py", "scripts/stage_hardening.py",
          "scripts/detector_lg3.py", "datasets/external/orbench.v1.jsonl", "datasets/external/xstest.v1.jsonl",
          "datasets/external/jbb.v1.jsonl")
PREREG = "evals/validation/v1/PREREG_stage_hardening.md"
DIR = ROOT / "evals/validation/v1/stage_hardening"
SEAL = DIR / "prompts.seal.json"
RAW = DIR / "lg_raw.jsonl"
PILOT = DIR / "dev" / "pilot.jsonl"
OUT = ROOT / "evals/validation/v1/stage_hardening.json"
DATA_ROOT = None  # datasets/external; the tests point it at synthetic rows
PILOT_PADDED = 5  # pilot prompts that also get the padded form


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _rel(path: pathlib.Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _append(path: pathlib.Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _lg3():
    """scripts/detector_lg3.py: the Ollama transport, the one-job-at-a-time check and the call."""
    spec = importlib.util.spec_from_file_location("detector_lg3", ROOT / "scripts" / "detector_lg3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_pins() -> dict[str, str]:
    """{path: its git object id at HEAD} for PINNED. Refuses a path modified in the working tree or not committed."""
    if _git("status", "--porcelain", "--", *PINNED):
        raise SystemExit("pinned code or data is modified in the working tree: commit it first")
    pins = {path: _git("rev-parse", "--verify", "--quiet", f"HEAD:{path}") for path in PINNED}
    missing = [path for path, oid in pins.items() if not oid]
    if missing:
        raise SystemExit(f"not committed: {', '.join(missing)}")
    return pins


def committed(*paths: str) -> None:
    tracked = set(_git("ls-files", "--", *paths).splitlines())
    missing = [path for path in paths if path not in tracked]
    if missing:
        raise SystemExit(f"not committed: {', '.join(missing)}")
    if _git("status", "--porcelain", "--", *paths):
        raise SystemExit(f"modified in the working tree, commit first: {', '.join(paths)}")


def prompts_of(text: str, stage: LlamaGuard) -> list[str]:
    """Every distinct prompt either arm sends for one text: the raw one, then the shipped stage's."""
    return list(dict.fromkeys([sh.raw_prompt(text), *sh.hardened_prompts(text, stage)]))


def sealed_units() -> list[dict]:
    """The registered units, each with the sha256 of every prompt either arm sends for it."""
    stage = LlamaGuard()
    return [{**u, "prompt_sha256": [_sha(p) for p in prompts_of(u["text"], stage)]}
            for u in sh.units(sh.held_back(DATA_ROOT))]


def pilot_units(n: int) -> list[dict]:
    """Development units: the first `n` unsafe JBB prompts (seen in the content-safety study) in every attack form,
    the padded form on the first `PILOT_PADDED` only."""
    rows = sorted((r for r in experiments._load("jbb", DATA_ROOT) if r["label"] == "unsafe"), key=lambda r: r["id"])
    out = []
    for i, r in enumerate(rows[:n]):
        for name, form in sh.ATTACKS.items():
            if name != "padded" or i < PILOT_PADDED:
                out.append({"id": f"{r['id']}::{name}", "label": "unsafe", "form": name, "text": form(r["prompt"])})
    return out


def _ready(transport) -> str:
    """The registered model's digest; refuses when it is missing or another model is loaded (one job at a time)."""
    lg3 = _lg3()
    digest = lg3.installed_digest(transport, LLAMA_GUARD_MODEL)
    if not digest:
        raise SystemExit(f"{LLAMA_GUARD_MODEL} is not installed in Ollama")
    others = lg3.other_models(transport, LLAMA_GUARD_MODEL)
    if others:
        raise SystemExit(f"Ollama has other models loaded ({', '.join(others)}): one job at a time")
    return digest


def record_replies(units: list[dict], path: pathlib.Path, transport) -> int:
    """Ask Llama Guard every prompt of `units` not yet in `path`; one record per distinct prompt. Resumable."""
    lg3, stage = _lg3(), LlamaGuard()
    digest = _ready(transport)
    done = {r["prompt_sha256"] for r in _jsonl(path)}
    asked = 0
    for unit in units:
        for prompt in prompts_of(unit["text"], stage):
            key = _sha(prompt)
            if key in done:
                continue
            start = time.perf_counter()
            output = lg3.ask(transport, LLAMA_GUARD_MODEL, prompt)
            _append(path, {"unit": unit["id"], "prompt_sha256": key, "output": output, "lg_model": LLAMA_GUARD_MODEL,
                           "digest": digest, "seconds": round(time.perf_counter() - start, 2)})
            done.add(key)
            asked += 1
    return asked


def unit_rows(units: list[dict], records: list[dict]) -> list[dict]:
    """Each unit as both arms judged it, from the recorded replies (`stage_hardening.flags`)."""
    replies = {r["prompt_sha256"]: r["output"] for r in records}
    rows = []
    for unit in units:
        flag = sh.flags(unit["text"], replies)
        rows.append({"id": unit["id"], "label": unit["label"], "form": unit["form"],
                     "category": unit.get("category", ""),
                     "systems": {sh.RAW: flag[sh.RAW], sh.HARDENED: flag[sh.HARDENED]}, "no_verdict": flag["no_verdict"]})
    return rows


def _table(doc: dict) -> str:
    lines = []
    for label in ("unsafe", "safe"):
        for form, block in doc[label].items():
            raw, hard, pair = block["systems"][sh.RAW], block["systems"][sh.HARDENED], block["paired"]
            lines.append(f"  {label:6} {form:15} n={block['n']:3}  raw {raw['k']:3}  hardened {hard['k']:3}  "
                         f"raw only {pair['reference_only']:3}  hardened only {pair['other_only']:3}  "
                         f"p={pair['mcnemar_p']:.4g}")
    return "\n".join(lines)


def cmd_plan(a) -> int:
    units = sealed_units()
    calls = len({k for u in units for k in u["prompt_sha256"]})
    done = {r["prompt_sha256"] for r in _jsonl(RAW)}
    print(f"units: {len(units)} ({sum(u['label'] == 'unsafe' for u in units)} unsafe, "
          f"{sum(u['label'] == 'safe' for u in units)} safe); distinct prompts to classify: {calls}")
    print(f"registration: {'committed' if _git('ls-files', '--', PREREG) else 'not yet'}; seal: "
          f"{'written' if SEAL.is_file() else 'not yet'}; classified: {len(done)} of {calls}; scored: {OUT.is_file()}")
    print(f"pilot: {len(_jsonl(PILOT))} replies recorded ({_rel(PILOT)})")
    return 0


def cmd_pilot(a, transport) -> int:
    units = pilot_units(a.n)
    asked = record_replies(units, PILOT, transport)
    doc = sh.score(unit_rows(units, _jsonl(PILOT)))
    print(f"pilot (development, seen prompts, never quoted): {asked} new replies\n{_table(doc)}")
    return 0


def cmd_seal(a) -> int:
    if SEAL.is_file():
        raise SystemExit(f"{_rel(SEAL)} exists: a seal is written once")
    units = sealed_units()
    seal = compute_seal(units)
    write_seal(SEAL, seal, {"study": "stage_hardening", "sealed": _dt.date.today().isoformat(),
                            "n": {"units": len(units), **sh.N, "padded": sh.PADDED_N}, "code": code_pins(),
                            "lg_model": LLAMA_GUARD_MODEL})
    print(f"sealed {len(seal)} units, digest {seal_digest(seal)}")
    return 0


def _registered() -> list[dict]:
    """The sealed units, only in the registered tree: registration and seal committed, pins unchanged, rows intact."""
    committed(PREREG, _rel(SEAL))
    if code_pins() != load_seal_meta(SEAL).get("code"):
        raise SystemExit("the pinned code or data changed since the seal: this tree is not the registered one")
    units = sealed_units()
    drift = verify_seal(units, load_seal(SEAL))
    if any(drift.values()):
        raise SystemExit(f"the units differ from the seal: {drift}")
    return units


def cmd_classify(a, transport) -> int:
    units = _registered()
    asked = record_replies(units, RAW, transport)
    print(f"{asked} new replies; {len(_jsonl(RAW))} recorded in {_rel(RAW)}. Commit it unscored.")
    return 0


def cmd_score(a) -> int:
    if OUT.is_file():
        raise SystemExit(f"{_rel(OUT)} exists: scored once")
    units = _registered()
    committed(_rel(RAW))
    records = _jsonl(RAW)
    rows = unit_rows(units, records)
    doc = sh.score(rows)
    out = {"kind": "stage_hardening", "preregistration": PREREG, "measured": _dt.date.today().isoformat(),
           "git_sha": _git("rev-parse", "HEAD"), "seal_digest": seal_digest(load_seal(SEAL)),
           "llama_guard": {"model": LLAMA_GUARD_MODEL, "digest": sorted({r["digest"] for r in records}),
                           "replies": len(records),
                           "unparseable": sum(parse_verdict(r["output"])["label"] == "unparseable" for r in records),
                           "median_seconds": statistics.median(r["seconds"] for r in records)},
           **doc, "decision": sh.decision(doc), "rows": rows}
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {_rel(OUT)}\n{_table(doc)}\n{json.dumps(out['decision'], indent=2)}")
    return 0


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "seal", "classify", "score"):
        sub.add_parser(name)
    sub.add_parser("pilot").add_argument("--n", type=int, default=20)
    a = parser.parse_args(argv)
    if a.cmd in ("pilot", "classify"):
        return {"pilot": cmd_pilot, "classify": cmd_classify}[a.cmd](a, transport or _lg3().http_transport())
    return {"plan": cmd_plan, "seal": cmd_seal, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
