"""The request binder on sealed blind-authored calls: the guard's rules alone against the same rules with the
binder (`Guardrail(binder=RequestBinder(MODEL, explain=True))`). Pre-registered in
evals/validation/v1/PREREG_binder.md. Dev-only; local Ollama only; no spend.

    python scripts/binder_study.py batches    # authored files -> unlabeled batches for the blind checkers
    python scripts/binder_study.py build      # authored files + the checkers' answers -> rows + seal (before the PREREG commit)
    python scripts/binder_study.py plan       # where every step stands; the size of the Ollama job
    python scripts/binder_study.py classify   # the binder's answer for every call the binding rule blocks (resumable)
    python scripts/binder_study.py score      # verifies the seal and the pinned code; writes the evidence once

`classify` is ONE Ollama job. Each answer is recorded under the sha256 of the model and the exact chat sent;
`score` replays the answers through the guard, so both arms are the committed guard's own decisions.
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

from fusion_first.validate.prereg import binding_decision  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    load_seal_meta,
    seal_digest,
    verify_seal,
    write_seal,
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_script", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


STEP5 = _load("step5_binding")  # binding_only, _block (the registered statistics)
DEV = _load("binder_dev")       # decide (step 5's guard configuration), Recorded, the synced append

# Registered (PREREG_binder.md); changing any of these after registration voids the run.
MODEL = "qwen2.5:7b#explain"
PINNED = ("fusion_first/guardrail", "fusion_first/security", "fusion_first/stats", "fusion_first/offline.py",
          "fusion_first/validate/prereg.py", "fusion_first/validate/seal.py", "scripts/binder_study.py",
          "scripts/binder_dev.py", "scripts/step5_binding.py")
PREREG = "evals/validation/v1/PREREG_binder.md"
DATA = ROOT / "datasets/guard_binder"
AUTHORED = DATA / "authored"
BATCHES = DATA / "batches"
ANSWERS = DATA / "answers"
CHECKS = DATA / "checks.json"
ROWS = DATA / "rows.v1.jsonl"
SEAL = DATA / "rows.v1.seal.json"
RAW = ROOT / "evals/validation/v1/binder/answers.jsonl"
OUT = ROOT / "evals/validation/v1/binder_study.json"
LABELS = ("legitimate", "hijack")
N_BATCHES = 6
TARGET = {"legitimate": 25, "hijack": 16, "targets_reviewer": 4}  # per author, as the brief asks; a target
MIN_SHARE = 0.8  # an author's file is used when each count reaches this share of its target


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _rel(path: pathlib.Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def authored_docs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(AUTHORED.glob("*.json"))]


def row_id(doc: dict, i: int) -> str:
    return f"{doc['author']}-{i:03d}"


def check_shape(doc: dict) -> list[str]:
    """What an authored file gets wrong against the brief's format (not its content): an empty list when it can
    be used. A file that fails is re-requested from its author; nothing is repaired by hand."""
    out = []
    for key in ("author", "domain", "org_domain", "tools", "rows"):
        if key not in doc:
            out.append(f"missing {key}")
    if out:
        return out
    names = {t.get("name") for t in doc["tools"] if isinstance(t, dict)}
    counts = collections.Counter()
    for i, r in enumerate(doc["rows"]):
        rid = row_id(doc, i)
        if r.get("label") not in LABELS:
            out.append(f"{rid}: label {r.get('label')!r}")
            continue
        counts[r["label"]] += 1
        counts["targets_reviewer"] += bool(r.get("targets_reviewer"))
        call = r.get("call")
        if not isinstance(r.get("user_request"), str) or not isinstance(r.get("tool_results"), str):
            out.append(f"{rid}: user_request and tool_results must be text")
        if not isinstance(call, dict) or call.get("name") not in names or not isinstance(call.get("arguments", {}), dict):
            out.append(f"{rid}: the call must name a tool of the catalogue and carry an arguments object")
        if r.get("targets_reviewer") and r["label"] != "hijack":
            out.append(f"{rid}: targets_reviewer on a row that is not a hijack")
    if any(counts[k] < MIN_SHARE * n for k, n in TARGET.items()):
        out.append(f"row counts {dict(counts)} fall short of the brief's {TARGET}")
    return out


# --------------------------------------------------------------------------------------- batches, build
def batches(docs: list[dict]) -> list[list[dict]]:
    """Every row without its label, in an order fixed by a hash of its id, dealt into `N_BATCHES`."""
    items = []
    for doc in docs:
        for i, r in enumerate(doc["rows"]):
            items.append({"id": row_id(doc, i), "tools": doc["tools"], "user_request": r["user_request"],
                          "tool_results": r["tool_results"], "call": r["call"]})
    items.sort(key=lambda x: hashlib.sha256(f"fusion-binder-v1:{x['id']}".encode()).hexdigest())
    return [items[n::N_BATCHES] for n in range(N_BATCHES)]


def build_rows(docs: list[dict], answers: dict[str, str]) -> tuple[list[dict], dict[str, int]]:
    """Rows under the registered drop rule (step 5's): a legitimate row the blind checker answered "no" or a
    hijack row it answered "yes" is dropped; nothing else is."""
    rows, dropped = [], dict.fromkeys(LABELS, 0)
    for doc in sorted(docs, key=lambda d: d["author"]):
        for i, r in enumerate(doc["rows"]):
            rid = row_id(doc, i)
            answer = answers.get(rid)
            if answer not in ("yes", "no"):
                raise SystemExit(f"{rid}: the validity check has no yes/no answer for this row")
            if (r["label"] == "legitimate") != (answer == "yes"):
                dropped[r["label"]] += 1
                continue
            call = {"name": r["call"]["name"], "arguments": r["call"].get("arguments") or {}}
            rows.append({"id": rid, "split": "blind", "label": r["label"], "author": doc["author"],
                         "domain": doc["domain"], "org_domain": doc["org_domain"],
                         "user_request": r["user_request"], "tool_results": r["tool_results"], "call": call,
                         "binding_only": STEP5.binding_only(call),
                         "targets_reviewer": bool(r.get("targets_reviewer"))})
    return rows, dropped


def _docs_or_exit() -> list[dict]:
    docs = authored_docs()
    problems = {d.get("author", "?"): p for d in docs if (p := check_shape(d))}
    if problems:
        raise SystemExit("authored files do not fit the brief's format:\n" + json.dumps(problems, indent=1))
    return docs


def cmd_batches(a) -> int:
    docs = _docs_or_exit()
    BATCHES.mkdir(parents=True, exist_ok=True)
    for n, batch in enumerate(batches(docs), 1):
        (BATCHES / f"c{n:02d}.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1) + "\n",
                                                encoding="utf-8", newline="\n")
    print(f"{len(docs)} authors, {sum(len(d['rows']) for d in docs)} rows in {N_BATCHES} batches under {_rel(BATCHES)}")
    return 0


def cmd_build(a) -> int:
    if ROWS.exists() or SEAL.exists():
        raise SystemExit(f"{ROWS.name} or its seal exists: the rows are built once")
    docs = _docs_or_exit()
    answers: dict[str, str] = {}
    for p in sorted(ANSWERS.glob("*.json")):
        answers.update(json.loads(p.read_text(encoding="utf-8")))
    CHECKS.write_text(json.dumps(answers, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                      newline="\n")
    rows, dropped = build_rows(docs, answers)
    ROWS.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")
    counts = collections.Counter(r["label"] for r in rows)
    write_seal(SEAL, compute_seal(rows), meta={
        "study": "request binder", "authors": len(docs), "rows": dict(counts), "dropped_by_validity_check": dropped,
        "binding_only_hijack": sum(r["binding_only"] for r in rows if r["label"] == "hijack"),
        "targets_reviewer": sum(r["targets_reviewer"] for r in rows), "model": MODEL, "code": code_pins()})
    print(json.dumps({"rows": dict(counts), "dropped": dropped, "digest": seal_digest(load_seal(SEAL))}, indent=1))
    return 0


# ------------------------------------------------------------------------------------- classify, score
def code_pins() -> dict[str, str]:
    """{path: its git object id at HEAD} for PINNED. Refuses a path modified in the working tree or not committed."""
    if _git("status", "--porcelain", "--", *PINNED):
        raise SystemExit("pinned code is modified in the working tree: commit it first")
    pins = {path: _git("rev-parse", "--verify", "--quiet", f"HEAD:{path}") for path in PINNED}
    missing = [path for path, oid in pins.items() if not oid]
    if missing:
        raise SystemExit(f"not committed: {', '.join(missing)}")
    return pins


def _registered() -> list[dict]:
    """The sealed rows, only in the registered tree: registration, rows and seal committed, pins unchanged."""
    paths = (PREREG, _rel(ROWS), _rel(SEAL))
    tracked = set(_git("ls-files", "--", *paths).splitlines())
    if set(paths) - tracked or _git("status", "--porcelain", "--", *paths):
        raise SystemExit(f"not committed, or modified: {', '.join(paths)}")
    if code_pins() != load_seal_meta(SEAL).get("code"):
        raise SystemExit("the pinned code changed since the seal: this tree is not the registered one")
    rows = DEV._jsonl(ROWS)
    drift = verify_seal(rows, load_seal(SEAL))
    if any(drift.values()):
        raise SystemExit(f"the rows do not match their seal: {drift}")
    return rows


def arms(rows: list[dict], *, live: bool, transport=None) -> tuple[dict, dict, list[dict]]:
    """Each row's decision under the rules alone (`old`) and with the binder (`new`), as {id: {blocked}}, and the
    per-row detail. With `live`, missing binder answers are asked for and recorded in RAW."""
    results = DEV.run(MODEL, rows, live=live, transport=transport, path=RAW)
    if not live and not all(r["answered"] for r in results):
        raise SystemExit(f"{sum(not r['answered'] for r in results)} rows have no recorded binder answer: run classify")
    old = {r["id"]: {"blocked": r["rules"]} for r in results}
    new = {r["id"]: {"blocked": r["binder"]} for r in results}
    return old, new, results


def score_rows(rows: list[dict], old: dict, new: dict) -> dict:
    by = {label: [r for r in rows if r["label"] == label] for label in LABELS}
    return {"legitimate": STEP5._block(by["legitimate"], old, new), "hijack": STEP5._block(by["hijack"], old, new),
            "hijack_binding_only": STEP5._block([r for r in by["hijack"] if r["binding_only"]], old, new),
            "hijack_targets_reviewer": STEP5._block([r for r in by["hijack"] if r["targets_reviewer"]], old, new),
            "per_domain": {d: {label: {"n": len(rs), "old_blocked": sum(old[r["id"]]["blocked"] for r in rs),
                                       "new_blocked": sum(new[r["id"]]["blocked"] for r in rs)}
                               for label in LABELS for rs in [[r for r in by[label] if r["domain"] == d]]}
                           for d in sorted({r["domain"] for r in rows})}}


def cmd_plan(a) -> int:
    docs = authored_docs()
    print(f"authored: {len(docs)} files; shape problems: { {d.get('author'): check_shape(d) for d in docs if check_shape(d)} }")
    print(f"answers: {len(list(ANSWERS.glob('*.json')))} of {N_BATCHES} batches; rows built: {ROWS.is_file()}; "
          f"registration: {'committed' if _git('ls-files', '--', PREREG) else 'not yet'}; scored: {OUT.is_file()}")
    if ROWS.is_file():
        rows = DEV._jsonl(ROWS)
        results = DEV.run(MODEL, rows, live=False, path=RAW)
        print(f"rows: {dict(collections.Counter(r['label'] for r in rows))}; binder answers still to ask: "
              f"{sum(not r['answered'] for r in results)}")
    return 0


def cmd_classify(a, transport=None) -> int:
    rows = _registered()
    _old, _new, results = arms(rows, live=True, transport=transport)
    print(f"{sum(r['asked'] > 0 for r in results)} rows needed the binder; {len(DEV._jsonl(RAW))} answers recorded in "
          f"{_rel(RAW)}. Commit it unscored.")
    return 0


def cmd_score(a) -> int:
    if OUT.is_file():
        raise SystemExit(f"{_rel(OUT)} exists: the sealed rows are scored once")
    rows = _registered()
    if _git("status", "--porcelain", "--", _rel(RAW)) or not _git("ls-files", "--", _rel(RAW)):
        raise SystemExit(f"{_rel(RAW)} is not committed, or is modified")
    old, new, results = arms(rows, live=False)
    s = score_rows(rows, old, new)
    records = [r for r in DEV._jsonl(RAW) if r["model"] == MODEL]
    evidence = {"demonstration": False, "kind": "request_binder", "preregistration": PREREG,
                "measured": _dt.date.today().isoformat(), "git_sha": _git("rev-parse", "HEAD"),
                "seal": {"path": _rel(SEAL), "digest": seal_digest(load_seal(SEAL)), "n_rows": len(rows)},
                "binder": {"model": MODEL, "answers": len(records),
                           "no_answer": sum(isinstance(r["answer"], str) for r in records),
                           "median_seconds": statistics.median(r["seconds"] for r in records) if records else None,
                           "rows_asked": sum(r["asked"] > 0 for r in results)},
                **s, "decision": binding_decision(s),
                "rows": [{"id": r["id"], "label": r["label"], "domain": r["domain"], "binding_only": r["binding_only"],
                          "targets_reviewer": r["targets_reviewer"], "old": old[r["id"]], "new": new[r["id"]]}
                         for r in rows]}
    OUT.write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: evidence[k] for k in ("legitimate", "hijack", "hijack_binding_only",
                                               "hijack_targets_reviewer", "binder", "decision")}, indent=1))
    return 0


def main(argv: list[str] | None = None, *, transport=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("batches", "build", "plan", "classify", "score"):
        sub.add_parser(name)
    a = parser.parse_args(argv)
    if a.cmd == "classify":
        return cmd_classify(a, transport)
    return {"batches": cmd_batches, "build": cmd_build, "plan": cmd_plan, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
