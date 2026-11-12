"""The guard's content-safety stage on fresh prompts: the guard alone, the guard with the stage (Llama Guard 3 under
Meta's categories) and the guard with the tuned stage. Pre-registered in
evals/validation/v1/PREREG_content_stage.md. Dev-only; local Ollama only; no spend.

    python scripts/content_stage.py plan                        # where every step stands; the size of each Ollama job
    python scripts/content_stage.py smoke [--n 20]              # the shipped stage, live, against recorded replies
    python scripts/content_stage.py dev --candidate NAME        # tuning: one candidate on the 650 seen prompts
    python scripts/content_stage.py select                      # tuning: apply the selection rule, once
    python scripts/content_stage.py seal                        # write the seal (before the registration commit)
    python scripts/content_stage.py classify --arm stage|tuned  # Llama Guard's replies on the sealed prompts
    python scripts/content_stage.py score                       # verifies the seal and every record; writes once

Tuning is development on seen prompts (the 650 of PREREG_content_safety.md): each candidate in
`guard_compare.TUNING_CANDIDATES` runs once, the default policy's numbers are that study's recorded replies, and
`select` applies `guard_compare.select_tuned`. The test is on fresh OR-Bench prompts: `classify` records Llama Guard's
raw reply to the exact prompt the shipped stage builds (`fusion_first.guardrail.stages.LlamaGuard.prompt`), raw mode,
temperature 0, as `scripts/detector_lg3.py`; `score` replays those replies through the shipped
`Guardrail.guard_prompt`, so the flags are the shipped code's. `smoke`, `dev` and `classify` are ONE Ollama job each:
they refuse any model but the registered one and refuse while Ollama has another model loaded.
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

from fusion_first.guardrail.guard import NO_VERDICT, Guardrail  # noqa: E402
from fusion_first.guardrail.stages import LlamaGuard, parse_verdict  # noqa: E402
from fusion_first.validate import guard_compare as gc  # noqa: E402
from fusion_first.validate.llama_guard import MODEL as LG_MODEL  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    seal_digest,
    verify_seal,
    write_seal,
)

# Registered (PREREG_content_stage.md); changing any of these after registration voids the run.
GUARD_SHA = "db3ebc15535777128f34cdfc8ffea140a6f98882"  # the stage as shipped: last commit to fusion_first/guardrail
RULE_PATHS = ("fusion_first/guardrail",)
PINNED = (*RULE_PATHS, "datasets/external/orbench.v1.jsonl", "datasets/external/xstest.v1.jsonl",
          "datasets/external/jbb.v1.jsonl", "scripts/content_stage.py", "fusion_first/validate/guard_compare.py",
          "fusion_first/validate/llama_guard.py", "fusion_first/validate/prereg.py")
PREREG = "evals/validation/v1/PREREG_content_stage.md"
DIR = ROOT / "evals/validation/v1/content_stage"
DEV_DIR = DIR / "dev"
SELECTION = DEV_DIR / "selection.json"
SEAL = DIR / "prompts.seal.json"
OUT = ROOT / "evals/validation/v1/content_stage.json"
SEEN_RAW = ROOT / "evals/validation/v1/content_safety/lg_raw.jsonl"  # the default policy on the seen prompts
SEEN_EVIDENCE = ROOT / "evals/validation/v1/content_safety.json"
DATA_ROOT = None  # datasets/external; the tests point it at synthetic rows
LG_ARMS = (gc.STAGE_DEFAULT, gc.STAGE_TUNED)


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
    """scripts/detector_lg3.py: the Ollama transport, the one-job-at-a-time check and the retrying call."""
    spec = importlib.util.spec_from_file_location("detector_lg3", ROOT / "scripts" / "detector_lg3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def raw_path(arm: str) -> pathlib.Path:
    return DIR / f"lg_raw.{arm}.jsonl"


def dev_path(candidate: str) -> pathlib.Path:
    return DEV_DIR / f"{candidate}.jsonl"


def policies(tuned: str | None) -> dict[str, tuple[str, ...]]:
    """{arm: its category lines}: the stage under Meta's categories and, when the tuning round produced one, under
    the tuned policy."""
    out = {gc.STAGE_DEFAULT: gc.STAGE_POLICIES["default"]}
    if tuned is not None:
        if tuned not in gc.TUNING_CANDIDATES:
            raise ValueError(f"{tuned!r} is not a tuning candidate (one of {', '.join(gc.TUNING_CANDIDATES)})")
        out[gc.STAGE_TUNED] = gc.STAGE_POLICIES[tuned]
    return out


def _policy_block(name: str, *, spell_out: bool) -> dict:
    lines = gc.STAGE_POLICIES[name]
    block = {"policy": name, "categories_sha256": prompt_sha256("\n".join(lines))}
    return {"policy": name, "categories": list(lines), "categories_sha256": block["categories_sha256"]} if spell_out \
        else block


def selection() -> dict:
    """What the tuning round selected (`select` writes it once)."""
    if not SELECTION.is_file():
        raise SystemExit(f"no selection at {_rel(SELECTION)}: run `select` first (it closes the tuning round)")
    return json.loads(SELECTION.read_text(encoding="utf-8"))


def seen_rows() -> list[dict]:
    """The 650 prompts of the content-safety study: development data here."""
    return gc.content_rows(DATA_ROOT)


def rows(root=None, *, tuned: str | None) -> list[dict]:
    """The registered sample, each prompt with the hash of the exact Llama Guard prompt of every arm."""
    stages = {arm: LlamaGuard(categories=lines) for arm, lines in policies(tuned).items()}
    return [{**r, "lg_prompt_sha256": {arm: prompt_sha256(stage.prompt(r["prompt"])) for arm, stage in stages.items()}}
            for r in gc.stage_rows(DATA_ROOT if root is None else root)]


def sealed_rows() -> tuple[list[dict], str, str | None]:
    """(the prompts, the seal's digest, the tuned policy or None), only when they match the seal exactly."""
    tuned = selection()["tuned"]
    if not SEAL.is_file():
        raise SystemExit(f"no seal at {_rel(SEAL)}: run `seal` and commit it with the registration first")
    seal = load_seal(SEAL)
    rs = rows(tuned=tuned)
    drift = verify_seal(rs, seal)
    if any(drift.values()):
        raise SystemExit(f"the prompts do not match their seal: { {k: v[:3] for k, v in drift.items() if v} }")
    return rs, seal_digest(seal), tuned


def verdicts(rs: list[dict], records: list[dict], arm: str) -> dict[str, dict]:
    """{prompt id: its Llama Guard record for `arm`}. Refuses a duplicate, a record of another arm, one made from
    another prompt, by another model or by more than one set of weights, a stored verdict its output does not give,
    and a prompt with no record."""
    by_id = {r["id"]: r for r in rs}
    out: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("id")
        if rid not in by_id:
            raise ValueError(f"{rid}: a record for a prompt that is not registered")
        if rid in out:
            raise ValueError(f"{rid}: recorded twice")
        if rec.get("arm") != arm:
            raise ValueError(f"{rid}: recorded for the {rec.get('arm')!r} arm, not {arm!r}")
        if rec.get("lg_model") != LG_MODEL:
            raise ValueError(f"{rid}: recorded by {rec.get('lg_model')!r}, not the registered {LG_MODEL!r}")
        if rec.get("prompt_sha256") != by_id[rid]["lg_prompt_sha256"][arm]:
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


def evidence(rs: list[dict], records: dict[str, list[dict]], *, digest: str, tuned: str | None,
             sample: dict | None = None, tuning: dict | None = None) -> dict:
    """The evidence document from the sealed prompts and each arm's raw records (no git, no clock: `cmd_score` adds
    them). Every flag comes from the shipped guard, its classifier replaying the arm's recorded reply."""
    arms = policies(tuned)
    if set(records) != set(arms):
        raise ValueError(f"records for the arms {sorted(records)}; the registered arms are {sorted(arms)}")
    by_arm = {arm: verdicts(rs, records[arm], arm) for arm in arms}
    digests = {rec["model_digest"] for recs in by_arm.values() for rec in recs.values()}
    if len(digests) != 1:
        raise ValueError(f"the arms name {len(digests)} model digests; one set of weights is registered")
    scored = [gc.stage_row(r, {arm: by_arm[arm][r["id"]] for arm in arms}, arms) for r in rs]

    def median_seconds(arm: str) -> float | None:
        seconds = [rec["seconds"] for rec in by_arm[arm].values() if isinstance(rec.get("seconds"), int | float)]
        return round(statistics.median(seconds), 3) if seconds else None

    arm_blocks = {gc.STAGE_GUARD: {"policy": None}, gc.STAGE_DEFAULT: _policy_block("default", spell_out=False)}
    if tuned is not None:
        arm_blocks[gc.STAGE_TUNED] = _policy_block(tuned, spell_out=True)
    return {
        "demonstration": False,
        "kind": ("the guard's content-safety stage on fresh harmful and benign prompts: the guard alone, with the "
                 "stage (Llama Guard 3, Meta's categories) and with the tuned stage"),
        "preregistration": PREREG,
        "llama_guard": {"model": LG_MODEL, "digest": next(iter(digests)),
                        "prompt": ("the shipped stage's prompt (fusion_first.guardrail.stages.LlamaGuard.prompt): "
                                   "Meta's format, one User turn, the User message assessed"),
                        "unparseable": {arm: sum(r["llama_guard"][arm]["label"] == "unparseable" for r in scored)
                                        for arm in arms},
                        "median_seconds": {arm: median_seconds(arm) for arm in arms}},
        "arms": arm_blocks,
        "fusion": {"configuration": ("default GuardConfig; a prompt is flagged when guard_prompt, guard_input "
                                     "(untrusted) or guard_output does anything but allow; each stage arm's "
                                     "classifier replays that arm's recorded Llama Guard reply")},
        "tuning": tuning,
        "sample": sample,
        "seal": {"path": _rel(SEAL), "n_rows": len(rs), "digest": digest},
        **gc.score_content_stage(scored),
        "rows": [{k: v for k, v in r.items() if k != "systems"} | {"flagged": r["systems"]} for r in scored],
    }


def assemble() -> dict:
    """What `score` writes, minus the date and the commit: the evidence from the committed selection, seal and raw
    records."""
    rs, digest, tuned = sealed_rows()
    records = {arm: _jsonl(raw_path(arm)) for arm in policies(tuned)}
    return evidence(rs, records, digest=digest, tuned=tuned, sample=gc.stage_sample(DATA_ROOT)[1], tuning=selection())


def dev_counts(policy: str, records: list[dict]) -> dict:
    """How the guard with the stage under `policy` flags the seen prompts, replaying `records`: one per prompt, each
    made from the exact prompt the stage sends under that policy."""
    by_id: dict[str, dict] = {}
    for rec in records:
        if rec.get("id") in by_id:
            raise ValueError(f"{rec.get('id')}: recorded twice")
        by_id[rec.get("id")] = rec
    rs = seen_rows()
    missing = [r["id"] for r in rs if r["id"] not in by_id]
    if missing:
        raise ValueError(f"no Llama Guard record for {len(missing)} seen prompt(s), first {missing[0]}")
    lines = {gc.STAGE_DEFAULT: gc.STAGE_POLICIES[policy]}
    out = {"safe_flagged": 0, "unsafe_flagged": 0, "n_safe": 0, "n_unsafe": 0, "unparseable": 0}
    for r in rs:
        row = gc.stage_row(r, {gc.STAGE_DEFAULT: by_id[r["id"]]}, lines)
        out[f"n_{r['label']}"] += 1
        out[f"{r['label']}_flagged"] += bool(row["systems"][gc.STAGE_DEFAULT])
        out["unparseable"] += row["llama_guard"][gc.STAGE_DEFAULT]["label"] == "unparseable"
    return out


# ------------------------------------------------------------------------------------------------ Ollama jobs
def _ready(model: str, force: bool, ollama: str | None, transport):
    """(the retrying call, the transport, the installed model's digest), once Ollama is free for this job."""
    if model != LG_MODEL:
        raise SystemExit(f"--model {model!r} is refused: the registered model is {LG_MODEL!r}")
    lg3 = _lg3()
    transport = transport or lg3.http_transport(ollama or lg3.OLLAMA)
    others = lg3.other_models(transport, model)
    if others and not force:
        raise SystemExit(f"Ollama has another model loaded ({', '.join(others)}): one Ollama job at a time")
    digest = lg3.installed_digest(transport, model)
    if not digest:
        raise SystemExit(f"{model} is not installed in Ollama")
    return lg3, transport, digest


def _record_replies(todo: list[dict], path: pathlib.Path, lines, tag: dict, model: str, lg3, transport,
                    digest: str) -> None:
    stage = LlamaGuard(model=model, categories=lines)
    for k, r in enumerate(todo, 1):
        prompt = stage.prompt(r["prompt"])
        output, seconds = lg3._timed(transport, model, prompt)
        rec = {"id": r["id"], **tag, "lg_model": model, "model_digest": digest, "prompt_sha256": prompt_sha256(prompt),
               "output": output, "verdict": parse_verdict(output)["label"], "seconds": round(seconds, 3)}
        _append(path, rec)
        print(f"{k}/{len(todo)} {r['id']}: {rec['verdict']} ({seconds:.1f} s)", flush=True)


def cmd_smoke(n: int, force: bool, ollama: str | None, transport=None) -> int:
    """The shipped stage end to end, live: `Guardrail(content_safety=LlamaGuard()).guard_prompt` on seen prompts,
    each verdict compared with the reply the content-safety study recorded for that prompt."""
    _, transport_used, digest = _ready(LG_MODEL, force, ollama, transport)
    recorded = {r["id"]: r for r in _jsonl(SEEN_RAW)}
    rs = seen_rows()
    pick = [r for r in rs if r["label"] == "unsafe"][:n // 2] + [r for r in rs if r["label"] == "safe"][:n - n // 2]
    stage = LlamaGuard(transport=transport_used) if transport is not None else LlamaGuard(base_url=ollama)
    guard = Guardrail(content_safety=stage)
    agree = no_verdict = 0
    for r in pick:
        outcome = guard.guard_prompt(r["prompt"])
        failed = any(e.detail.startswith(NO_VERDICT) for e in outcome.events)
        expected = parse_verdict(recorded[r["id"]]["output"])["label"] == "unsafe"
        no_verdict += failed
        agree += (not failed) and outcome.blocked == expected
        print(f"{r['id']}: {'no verdict' if failed else 'blocked' if outcome.blocked else 'allowed'} "
              f"(recorded: {'unsafe' if expected else 'safe'})", flush=True)
    print(json.dumps({"prompts": len(pick), "agree": agree, "no_verdict": no_verdict, "model_digest": digest,
                      "recorded_digest": next(iter(recorded.values()))["model_digest"] if recorded else None}))
    return 0 if pick and agree == len(pick) else 1


def cmd_dev(candidate: str, model: str, force: bool, ollama: str | None, transport=None) -> int:
    if candidate not in gc.TUNING_CANDIDATES:
        raise SystemExit(f"{candidate!r} is not a tuning candidate (one of {', '.join(gc.TUNING_CANDIDATES)})")
    if model != LG_MODEL:
        raise SystemExit(f"--model {model!r} is refused: the registered model is {LG_MODEL!r}")
    if SELECTION.exists() or SEAL.exists():
        raise SystemExit("the tuning round is closed: a selection or a seal exists")
    rs, path = seen_rows(), dev_path(candidate)
    done = {r["id"] for r in _jsonl(path)}
    todo = [r for r in rs if r["id"] not in done]
    if not todo:
        raise SystemExit(f"{candidate} has a reply for all {len(rs)} seen prompts: a candidate runs once")
    lg3, transport, digest = _ready(model, force, ollama, transport)
    _record_replies(todo, path, gc.STAGE_POLICIES[candidate], {"policy": candidate}, model, lg3, transport, digest)
    print(json.dumps({"candidate": candidate, "raw": _rel(path), "new": len(todo), "recorded": len(done) + len(todo)}))
    return 0


def cmd_select() -> int:
    if SELECTION.exists():
        raise SystemExit(f"{_rel(SELECTION)} exists: the selection rule is applied once")
    baseline_records = _jsonl(SEEN_RAW)
    weights = {r.get("model_digest") for r in baseline_records}
    baseline = dev_counts("default", baseline_records)
    counts, not_run = {}, []
    for name in gc.TUNING_CANDIDATES:
        records = _jsonl(dev_path(name))
        if not records:
            not_run.append(name)
            continue
        try:
            if {r.get("lg_model") for r in records} != {LG_MODEL}:
                raise ValueError(f"not every reply is from the registered {LG_MODEL!r}")
            if {r.get("model_digest") for r in records} != weights:
                raise ValueError("its replies come from other weights than the default policy's")
            counts[name] = dev_counts(name, records)
        except ValueError as exc:
            raise SystemExit(f"select: {name}: {exc}") from exc
    chosen = gc.select_tuned(baseline, counts)
    doc = {"development": True,
           "note": ("the tuning round on the 650 prompts of the content-safety study: seen data, used to pick the "
                    "tuned arm and not evidence of anything"),
           "llama_guard": {"model": LG_MODEL, "digest": next(iter(weights)) if len(weights) == 1 else None},
           "measured": _dt.date.today().isoformat(), **chosen, "not_run": not_run, "counts": counts,
           "policies": {name: _policy_block(name, spell_out=True) for name in counts}}
    SELECTION.parent.mkdir(parents=True, exist_ok=True)
    SELECTION.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"selection": _rel(SELECTION), "tuned": chosen["tuned"], "baseline": baseline,
                      "candidates": chosen["candidates"], "not_run": not_run}, indent=1))
    return 0


def cmd_seal() -> int:
    tuned = selection()["tuned"]
    if SEAL.exists():
        raise SystemExit(f"{_rel(SEAL)} exists: the prompts are sealed once")
    rs = rows(tuned=tuned)
    _, sample = gc.stage_sample(DATA_ROOT)
    arms = {arm: _policy_block("default" if arm == gc.STAGE_DEFAULT else tuned, spell_out=False)
            for arm in policies(tuned)}
    SEAL.parent.mkdir(parents=True, exist_ok=True)
    write_seal(SEAL, compute_seal(rs), meta={
        "study": "the guard's content-safety stage on fresh OR-Bench prompts",
        "rows": dict(sorted(collections.Counter(r["label"] for r in rs).items())), "sample": sample,
        "salt": gc.STAGE_SALT, "arms": arms, "llama_guard_model": LG_MODEL, "guardrail_git_sha": GUARD_SHA})
    print(json.dumps({"seal": _rel(SEAL), "rows": len(rs), "arms": sorted(arms), "sample": sample}))
    return 0


def cmd_classify(arm: str, model: str, force: bool, ollama: str | None, transport=None) -> int:
    if model != LG_MODEL:
        raise SystemExit(f"--model {model!r} is refused: the registered model is {LG_MODEL!r}")
    rs, _, tuned = sealed_rows()
    arms = policies(tuned)
    if arm not in arms:
        raise SystemExit(f"{arm!r} is not a registered arm of this study (registered: {', '.join(arms)})")
    path = raw_path(arm)
    done = {r["id"] for r in _jsonl(path)}
    todo = [r for r in rs if r["id"] not in done]
    if todo:
        lg3, transport, digest = _ready(model, force, ollama, transport)
        _record_replies(todo, path, arms[arm], {"arm": arm}, model, lg3, transport, digest)
    print(json.dumps({"arm": arm, "raw": _rel(path), "new": len(todo), "recorded": len(done) + len(todo)}))
    return 0


# ------------------------------------------------------------------------------------------------ plan and score
def cmd_plan() -> int:
    seconds = 2.0
    if SEEN_EVIDENCE.is_file():
        seconds = json.loads(SEEN_EVIDENCE.read_text(encoding="utf-8"))["llama_guard"]["median_seconds"] or seconds
    n_seen = len(seen_rows())
    dev = {name: len(_jsonl(dev_path(name))) for name in gc.TUNING_CANDIDATES}
    doc: dict = {"seconds_per_prompt": seconds,
                 "tuning": {"seen_prompts": n_seen, "recorded": dev, "selected": SELECTION.is_file(),
                            "minutes_per_candidate": round(n_seen * seconds / 60)}}
    if SELECTION.is_file():
        doc["tuning"]["tuned"] = selection()["tuned"]
    try:
        sample, info = gc.stage_sample(DATA_ROOT)
    except FileNotFoundError:
        doc["test"] = {"sample": "OR-Bench is not imported yet"}
    else:
        tuned = selection()["tuned"] if SELECTION.is_file() else None
        recorded = {arm: len(_jsonl(raw_path(arm))) for arm in (policies(tuned) if SELECTION.is_file() else LG_ARMS)}
        doc["test"] = {"prompts": len(sample), "sample": info, "sealed": SEAL.is_file(), "recorded": recorded,
                       "minutes_per_arm": round(len(sample) * seconds / 60), "scored": OUT.is_file()}
    print(json.dumps(doc, indent=1))
    return 0


def cmd_score() -> int:
    if OUT.exists():
        raise SystemExit(f"{_rel(OUT)} exists: the sealed prompts are scored once")
    tuned = selection()["tuned"]
    tracked = [*PINNED, _rel(SEAL), _rel(SELECTION), *(_rel(raw_path(arm)) for arm in policies(tuned))]
    if _git("status", "--porcelain", "--", *tracked):
        raise SystemExit("the rules, the prompts, the selection, the seal, the raw records or the scorer are modified "
                         "in the working tree: commit them first")
    rules = _git("log", "-1", "--format=%H", "--", *RULE_PATHS)
    if rules != GUARD_SHA:
        raise SystemExit(f"{RULE_PATHS} are at {rules}, not the registered {GUARD_SHA}")
    try:
        doc = assemble()
    except ValueError as exc:
        raise SystemExit(f"score: {exc}") from exc
    head = ("demonstration", "kind", "preregistration")
    doc = {**{k: doc[k] for k in head}, "measured": _dt.date.today().isoformat(), "git_sha": _git("rev-parse", "HEAD"),
           "guardrail_git_sha": rules, **{k: v for k, v in doc.items() if k not in head}}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for label in ("unsafe", "safe"):
        s = doc[label]["systems"]
        print(f"{label:6} n={doc[label]['n']}: " + ", ".join(f"{arm} flagged {s[arm]['k']}" for arm in s))
    d = doc["decision"]
    print(f"the stage: {d['stage']['verdict']} ({d['stage']['reason']})")
    print(f"the tuned policy: {d['tuned']['verdict']} ({d['tuned']['cost']['reason']}; "
          f"{d['tuned']['protection']['reason']})")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="content_stage", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    ollama = argparse.ArgumentParser(add_help=False)
    ollama.add_argument("--model", default=LG_MODEL)
    ollama.add_argument("--ollama", default=None)
    ollama.add_argument("--force", action="store_true", help="run although Ollama has another model loaded")
    sub.add_parser("plan")
    smoke = sub.add_parser("smoke", parents=[ollama])
    smoke.add_argument("--n", type=int, default=20)
    dev = sub.add_parser("dev", parents=[ollama])
    dev.add_argument("--candidate", required=True, choices=gc.TUNING_CANDIDATES)
    sub.add_parser("select")
    sub.add_parser("seal")
    classify = sub.add_parser("classify", parents=[ollama])
    classify.add_argument("--arm", required=True, choices=LG_ARMS)
    sub.add_parser("score")
    a = p.parse_args(argv)
    if a.cmd == "plan":
        return cmd_plan()
    if a.cmd == "smoke":
        if a.model != LG_MODEL:
            raise SystemExit(f"--model {a.model!r} is refused: the registered model is {LG_MODEL!r}")
        return cmd_smoke(a.n, a.force, a.ollama)
    if a.cmd == "dev":
        return cmd_dev(a.candidate, a.model, a.force, a.ollama)
    if a.cmd == "select":
        return cmd_select()
    if a.cmd == "seal":
        return cmd_seal()
    if a.cmd == "classify":
        return cmd_classify(a.arm, a.model, a.force, a.ollama)
    return cmd_score()


if __name__ == "__main__":
    raise SystemExit(main())
