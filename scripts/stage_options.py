"""Do the stage's changes after the stage-hardening study work on unseen prompts? The stage in four configurations
on fresh OR-Bench and IFEval prompts (`fusion_first/validate/stage_options.py`). Pre-registered in
evals/validation/v1/PREREG_stage_options.md. Dev-only; local Ollama only; no spend.

    python scripts/stage_options.py plan        # where every step stands; the size of the Ollama job
    python scripts/stage_options.py seal        # write the seal (before the registration commit)
    python scripts/stage_options.py classify    # Llama Guard's replies to every sealed prompt (resumable)
    python scripts/stage_options.py score       # verifies the seal and every record; writes once

`classify` is ONE Ollama job: it refuses any model but the registered one and refuses while Ollama has another model
loaded. Every reply is recorded under the sha256 of the exact prompt sent; `score` replays the replies through the
shipped guard and stage, so the flags are the shipped code's.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.guardrail.stages import LLAMA_GUARD_MODEL, parse_verdict  # noqa: E402
from fusion_first.validate import stage_options as so  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    load_seal_meta,
    seal_digest,
    verify_seal,
    write_seal,
)


def _study():
    """scripts/stage_hardening.py: git, jsonl, the synced append, the Ollama transport and the one-job check."""
    spec = importlib.util.spec_from_file_location("stage_hardening_script", ROOT / "scripts" / "stage_hardening.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _study()

# Everything a flag or a statistic depends on. `seal` records each path's git object id; `classify` and `score`
# refuse a tree in which any of them differs.
PINNED = ("fusion_first/guardrail", "fusion_first/security", "fusion_first/stats", "fusion_first/offline.py",
          "fusion_first/validate/stage_options.py", "fusion_first/validate/stage_hardening.py",
          "fusion_first/validate/guard_compare.py", "fusion_first/validate/seal.py",
          "fusion_first/validate/experiments.py", "scripts/stage_options.py", "scripts/stage_hardening.py",
          "scripts/detector_lg3.py", "datasets/external/orbench.v1.jsonl", "datasets/external/xstest.v1.jsonl",
          "datasets/external/jbb.v1.jsonl", "datasets/external/ifeval.v1.jsonl")
PREREG = "evals/validation/v1/PREREG_stage_options.md"
DIR = ROOT / "evals/validation/v1/stage_options"
SEAL = DIR / "prompts.seal.json"
RAW = DIR / "lg_raw.jsonl"
OUT = ROOT / "evals/validation/v1/stage_options.json"
DATA_ROOT = None  # datasets/external; the tests point it at synthetic rows


def code_pins() -> dict[str, str]:
    """{path: its git object id at HEAD} for PINNED. Refuses a path modified in the working tree or not committed."""
    if S._git("status", "--porcelain", "--", *PINNED):
        raise SystemExit("pinned code or data is modified in the working tree: commit it first")
    pins = {path: S._git("rev-parse", "--verify", "--quiet", f"HEAD:{path}") for path in PINNED}
    missing = [path for path, oid in pins.items() if not oid]
    if missing:
        raise SystemExit(f"not committed: {', '.join(missing)}")
    return pins


def prompts_of(unit: dict) -> list[str]:
    """Every distinct prompt the unit's arms send."""
    return list(dict.fromkeys(p for arm in unit["arms"] for p in so.prompts_for(unit["text"], arm)))


def sealed_units() -> list[dict]:
    """The registered units, each with the sha256 of every prompt its arms send."""
    rows = [*so.fresh(DATA_ROOT), *so.ordinary(DATA_ROOT)]
    return [{**u, "prompt_sha256": [S._sha(p) for p in prompts_of(u)]} for u in so.units(rows)]


def record_replies(units: list[dict], path: pathlib.Path, transport) -> int:
    """Ask Llama Guard every prompt of `units` not yet in `path`; one record per distinct prompt. Resumable."""
    lg3 = S._lg3()
    digest = S._ready(transport)
    done = {r["prompt_sha256"] for r in S._jsonl(path)}
    asked = 0
    for unit in units:
        for prompt in prompts_of(unit):
            key = S._sha(prompt)
            if key in done:
                continue
            start = time.perf_counter()
            output = lg3.ask(transport, LLAMA_GUARD_MODEL, prompt)
            S._append(path, {"unit": unit["id"], "prompt_sha256": key, "output": output,
                             "lg_model": LLAMA_GUARD_MODEL, "digest": digest,
                             "seconds": round(time.perf_counter() - start, 2)})
            done.add(key)
            asked += 1
    return asked


def unit_rows(units: list[dict], records: list[dict]) -> list[dict]:
    """Each unit as its arms judged it, from the recorded replies (`stage_options.flags`)."""
    replies = {r["prompt_sha256"]: r["output"] for r in records}
    rows = []
    for unit in units:
        flag = so.flags(unit["text"], unit["arms"], replies)
        rows.append({"id": unit["id"], "group": unit["group"], "label": unit["label"], "form": unit["form"],
                     "category": unit.get("category", ""), "arms": unit["arms"],
                     "systems": {arm: f["flagged"] for arm, f in flag.items()},
                     "calls": {arm: f["calls"] for arm, f in flag.items()},
                     "no_verdict": {arm: f["no_verdict"] for arm, f in flag.items()}})
    return rows


def _table(doc: dict) -> str:
    lines = []
    for group, forms in doc.items():
        for form, block in forms.items():
            flagged = "  ".join(f"{arm} {s['k']:3}" for arm, s in block["systems"].items())
            tests = "  ".join(f"{arm}: p={pair['mcnemar_p']:.4g} (-{pair['reference_only']} +{pair['other_only']})"
                              for arm, pair in block["paired"].items())
            lines.append(f"  {group:8} {form:17} n={block['n']:3}  {flagged}  |  {tests}  |  calls {block['mean_calls']}")
    return "\n".join(lines)


def cmd_plan(a) -> int:
    units = sealed_units()
    calls = len({k for u in units for k in u["prompt_sha256"]})
    done = {r["prompt_sha256"] for r in S._jsonl(RAW)}
    groups = {g: sum(u["group"] == g for u in units) for g in so.DESIGN}
    print(f"units: {len(units)} {groups}; distinct prompts to classify: {calls}")
    print(f"registration: {'committed' if S._git('ls-files', '--', PREREG) else 'not yet'}; seal: "
          f"{'written' if SEAL.is_file() else 'not yet'}; classified: {len(done)} of {calls}; scored: {OUT.is_file()}")
    return 0


def cmd_seal(a) -> int:
    if SEAL.is_file():
        raise SystemExit(f"{S._rel(SEAL)} exists: a seal is written once")
    units = sealed_units()
    seal = compute_seal(units)
    write_seal(SEAL, seal, {"study": "stage_options", "sealed": _dt.date.today().isoformat(),
                            "n": {"units": len(units), **so.N}, "code": code_pins(), "lg_model": LLAMA_GUARD_MODEL})
    print(f"sealed {len(seal)} units, digest {seal_digest(seal)}")
    return 0


def _registered() -> list[dict]:
    """The sealed units, only in the registered tree: registration and seal committed, pins unchanged, rows intact."""
    S.committed(PREREG, S._rel(SEAL))
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
    print(f"{asked} new replies; {len(S._jsonl(RAW))} recorded in {S._rel(RAW)}. Commit it unscored.")
    return 0


def cmd_score(a) -> int:
    if OUT.is_file():
        raise SystemExit(f"{S._rel(OUT)} exists: scored once")
    units = _registered()
    S.committed(S._rel(RAW))
    records = S._jsonl(RAW)
    rows = unit_rows(units, records)
    doc = so.score(rows)
    out = {"kind": "stage_options", "demonstration": False, "preregistration": PREREG,
           "measured": _dt.date.today().isoformat(), "git_sha": S._git("rev-parse", "HEAD"),
           "seal_digest": seal_digest(load_seal(SEAL)),
           "llama_guard": {"model": LLAMA_GUARD_MODEL, "digest": sorted({r["digest"] for r in records}),
                           "replies": len(records),
                           "unparseable": sum(parse_verdict(r["output"])["label"] == "unparseable" for r in records),
                           "median_seconds": statistics.median(r["seconds"] for r in records)},
           "groups": doc, "decision": so.decision(doc), "rows": rows}
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {S._rel(OUT)}\n{_table(doc)}\n{json.dumps(out['decision'], indent=2)}")
    return 0


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "seal", "classify", "score"):
        sub.add_parser(name)
    a = parser.parse_args(argv)
    if a.cmd == "classify":
        return cmd_classify(a, transport or S._lg3().http_transport())
    return {"plan": cmd_plan, "seal": cmd_seal, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
