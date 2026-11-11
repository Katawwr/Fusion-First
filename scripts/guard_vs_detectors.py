"""Fusion's runtime guard against dedicated injection detectors on fresh InjecAgent transcripts. Pre-registered in
evals/validation/v1/PREREG_guard_vs_detectors.md. Dev-only; local Ollama and local classifiers only; no spend.

    python scripts/guard_vs_detectors.py plan                                       # the sample, the arms, what is left
    python scripts/guard_vs_detectors.py dev                                        # development pass: SPENT rows only (CPU)
    python scripts/guard_vs_detectors.py seal                                       # write the seal (before the registration commit)
    python scripts/guard_vs_detectors.py transcripts --arm plain --model qwen2.5:7b # ONE Ollama job; resumable
    python scripts/guard_vs_detectors.py classify                                   # both classifiers on every text (CPU; resumable)
    python scripts/guard_vs_detectors.py llama-guard                                # Llama Guard 3 on the transcripts; ONE Ollama job
    python scripts/guard_vs_detectors.py score                                      # verifies everything; writes the evidence once

Each of the 150 registered ids runs on both target models in three arms (plain, enhanced, control: see
`fusion_first.validate.guard_compare.arm_items`), with the generation settings of steps 2 and 3. Transcripts go to
the committed store (evals/validation/v1/transcripts); the raw classifier and Llama Guard records go to
evals/validation/v1/guard_vs_detectors/. `score` re-derives every verdict from those files and refuses a transcript,
record or rule that is not the registered one. Every Ollama command refuses while another model is loaded.
"""

from __future__ import annotations

import argparse
import asyncio
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
from fusion_first.validate import injection_classifiers as ic  # noqa: E402
from fusion_first.validate.benign_actions import dev_attacker_tools  # noqa: E402
from fusion_first.validate.experiments import (  # noqa: E402
    SPENT_THROUGH_STEP2,
    SPENT_THROUGH_STEP3,
    build_items,
)
from fusion_first.validate.guard_on_transcripts import injecagent_outcome  # noqa: E402
from fusion_first.validate.llama_guard import MODEL as LG_MODEL  # noqa: E402
from fusion_first.validate.llama_guard import configured_prompt, parse_verdict  # noqa: E402
from fusion_first.validate.seal import (  # noqa: E402
    compute_seal,
    load_seal,
    seal_digest,
    verify_seal,
    write_seal,
)
from fusion_first.validate.transcripts import (  # noqa: E402
    STORE_DIR_DEFAULT,
    TranscriptStore,
    generate,
)

# Registered (PREREG_guard_vs_detectors.md); changing any of these after registration voids the run.
GUARD_SHA = "5a89479ca515c5bdf04164b98eaaf80b8639f881"  # the published rules and the harness
RULE_PATHS = ("fusion_first/guardrail", "fusion_first/validate/guard_on_transcripts.py")
STORE_ARM = "baseline"  # the system prompt as written
MAX_TOKENS, SEED, NUM_CTX = 256, 7, 8192  # as steps 2 and 3 (scripts/run_evidence.py)
PREREG = "evals/validation/v1/PREREG_guard_vs_detectors.md"
DIR = ROOT / "evals/validation/v1/guard_vs_detectors"
SEAL = DIR / "items.seal.json"
MODELS_FILE = DIR / "models.json"
CLF_RAW = DIR / "classifier_raw.jsonl"
LG_RAW = DIR / "lg_raw.jsonl"
DEV = DIR / "dev_spent.json"
OUT = ROOT / "evals/validation/v1/guard_vs_detectors.json"
STORE = ROOT / STORE_DIR_DEFAULT
PINNED = (*RULE_PATHS, "fusion_first/validate/guard_compare.py", "fusion_first/validate/injection_classifiers.py",
          "fusion_first/validate/llama_guard.py", "fusion_first/validate/prereg.py",
          "fusion_first/validate/experiments.py", "datasets/external/injecagent.v1.jsonl",
          "datasets/external/injecagent_enhanced.v1.jsonl", gc.CONTROL_DATA, gc.CONTROL_SEAL,
          "scripts/guard_vs_detectors.py")
SECONDS = {"qwen2.5:7b": 42.7, "llama3.1:8b": 25.7, LG_MODEL: 7.4}  # per call, from committed latencies


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _jsonl(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _append(path: pathlib.Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lg3():
    """scripts/detector_lg3.py: the Ollama transport, the one-job-at-a-time check and the retrying call."""
    spec = importlib.util.spec_from_file_location("detector_lg3", ROOT / "scripts" / "detector_lg3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------ the registered units
def lg_seen() -> set[str]:
    return gc.lg_seen_ids(json.loads((ROOT / gc.LG_SUBSAMPLE).read_text(encoding="utf-8"))["ids"])


def arms() -> dict:
    """The registered sample in its three arms."""
    return gc.arm_items(gc.study_ids(lg_seen()), gc.sealed_control_rows(ROOT / gc.CONTROL_DATA, ROOT / gc.CONTROL_SEAL))


def sealed_arms() -> tuple[dict, str]:
    """(the arms, the seal's digest), only when every prompt and tool result matches the seal exactly."""
    if not SEAL.is_file():
        raise SystemExit(f"no seal at {_rel(SEAL)}: run `seal` and commit it with the registration first")
    seal = load_seal(SEAL)
    a = arms()
    drift = verify_seal(gc.seal_rows(a), seal)
    if any(drift.values()):
        raise SystemExit(f"the items do not match their seal: { {k: v[:3] for k, v in drift.items() if v} }")
    return a, seal_digest(seal)


def unit_id(item_id: str, arm: str) -> str:
    return f"{item_id}@{arm}"


def texts(a: dict) -> dict[tuple[str, str], str]:
    """{(unit id, input): text} for every text a classifier reads: the tool result (registered) and the whole user
    turn (the sensitivity input)."""
    out = {}
    for arm in gc.ARMS:
        for it in a[arm]:
            out[(unit_id(it.item_id, arm), "tool_result")] = it.injected
            out[(unit_id(it.item_id, arm), "user_turn")] = it.user
    return out


def prompt_hash(item) -> str:
    """As the transcript store keys a generation: the system prompt and the user turn."""
    return _sha(item.system_for(STORE_ARM) + "\n\x00\n" + item.user)


def responses(a: dict, store: TranscriptStore, models=gc.MODELS) -> dict[tuple[str, str, str], str]:
    """{(arm, model, item id): the model's reply} for every registered transcript. Refuses a missing or failed
    transcript and one generated from another prompt."""
    out = {}
    for arm in gc.ARMS:
        for model in models:
            recs = store.load(gc.EXPERIMENT[arm], model)
            for it in a[arm]:
                rec = recs.get((it.item_id, STORE_ARM))
                if rec is None or rec.error or rec.response is None:
                    raise ValueError(f"missing transcript: {arm} {model} {it.item_id}")
                if rec.system_sha256 != prompt_hash(it):
                    raise ValueError(f"{arm} {model} {it.item_id}: generated from another prompt than the registered")
                out[(arm, model, it.item_id)] = rec.response
    return out


def lg_verdicts(a: dict, replies: dict, records: list[dict]) -> dict[tuple[str, str, str], dict]:
    """{(arm, model, item id): its Llama Guard record}, each checked against the registered prompt for that reply.
    Refuses a duplicate, a foreign or mismatched record, more than one set of weights and a missing record."""
    items = {(arm, it.item_id): it for arm in gc.ARMS for it in a[arm]}
    out: dict[tuple[str, str, str], dict] = {}
    for rec in records:
        key = (rec.get("arm"), rec.get("model"), rec.get("item_id"))
        if key not in replies:
            raise ValueError(f"{key}: a Llama Guard record for a transcript that is not registered")
        if key in out:
            raise ValueError(f"{key}: recorded twice")
        if rec.get("lg_model") != LG_MODEL:
            raise ValueError(f"{key}: recorded by {rec.get('lg_model')!r}, not the registered {LG_MODEL!r}")
        if rec.get("prompt_sha256") != _sha(configured_prompt(items[(key[0], key[2])], replies[key])):
            raise ValueError(f"{key}: the recorded prompt is not the registered one for this reply")
        if rec.get("verdict") != parse_verdict(rec.get("output"))["label"]:
            raise ValueError(f"{key}: the stored verdict does not follow from the output")
        out[key] = rec
    missing = sorted(k for k in replies if k not in out)
    if missing:
        raise ValueError(f"no Llama Guard record for {len(missing)} transcript(s), first {missing[0]}")
    digests = {rec.get("model_digest") for rec in out.values()}
    if len(digests) != 1 or None in digests:
        raise ValueError(f"the records name {len(digests)} model digests; one set of weights is registered")
    return out


def _median(values) -> float | None:
    xs = [v for v in values if isinstance(v, int | float)]
    return round(statistics.median(xs), 4) if xs else None


def evidence(a: dict, replies: dict, lg_records: list[dict], clf_records: list[dict], *, digest: str,
             models: dict[str, str], dev_tools=()) -> dict:
    """The evidence document from the sealed items, the transcripts and the raw records (no git, no clock, no model:
    `cmd_score` adds the first two)."""
    lg = lg_verdicts(a, replies, lg_records)
    all_texts = texts(a)
    flags = {name: ic.verified_flags(clf_records, ic.CLASSIFIERS[name], all_texts) for name in gc.CLASSIFIERS}
    items = {(arm, it.item_id): it for arm in gc.ARMS for it in a[arm]}

    def rows_with(kind: str) -> list[dict]:
        return [gc.transcript_row(arm, model, items[(arm, rid)], reply, lg_label=parse_verdict(lg[key]["output"])["label"],
                                  classifier_flags={c: flags[c][(unit_id(rid, arm), kind)] for c in gc.CLASSIFIERS})
                for key, reply in sorted(replies.items()) for arm, model, rid in [key]]

    rows = rows_with("tool_result")
    scored = gc.score_study(rows, dev_tools=dev_tools)
    turn = gc.score_study(rows_with("user_turn"), dev_tools=dev_tools)  # secondary: the classifiers given the whole turn
    by_kind = {kind: {c: {arm: {it.item_id: flags[c][(unit_id(it.item_id, arm), kind)] for it in a[arm]}
                          for arm in gc.ARMS} for c in gc.CLASSIFIERS} for kind in ic.INPUTS}
    seconds = {c: _median(r.get("seconds") for r in clf_records
                          if r.get("classifier") == c and r.get("input") == "tool_result") for c in gc.CLASSIFIERS}
    return {
        "demonstration": False,
        "kind": "runtime guard vs dedicated injection detectors and Llama Guard 3 on fresh InjecAgent transcripts",
        "preregistration": PREREG,
        "harness": gc.HARNESSES[gc.HARNESS],
        "models": dict(models),
        "generation": {"max_tokens": MAX_TOKENS, "seed": SEED, "num_ctx": NUM_CTX, "temperature": 0},
        "sample": {"salt": gc.SALT, "n_items": gc.N_ITEMS, "exclude": [list(x[:2]) for x in SPENT_THROUGH_STEP3],
                   "removed_llama_guard_subsample_ids": len(lg_seen()), "ids": [it.item_id for it in a["plain"]]},
        "seal": {"path": _rel(SEAL), "n_rows": sum(len(v) for v in a.values()), "digest": digest},
        "llama_guard": {"model": LG_MODEL, "digest": next(iter(lg.values()))["model_digest"],
                        "prompt": "configured as in step 2: Meta's format, 14 default categories plus S15 and S16, "
                                  "the agent's reply assessed",
                        "unparseable": sum(r["lg"] == "unparseable" for r in rows),
                        "median_seconds": _median(rec.get("seconds") for rec in lg.values())},
        "classifiers": {c: {"repo": s.repo, "revision": s.revision, "weights_sha256": s.weights_sha256,
                            "license": s.license, "labels": list(s.labels), "positive": list(s.positive),
                            "threshold": ic.THRESHOLD, "max_tokens": ic.MAX_TOKENS, "stride": ic.STRIDE,
                            "input": "the tool result alone", "median_seconds": seconds[c]}
                        for c, s in ((c, ic.CLASSIFIERS[c]) for c in gc.CLASSIFIERS)},
        **scored,
        "secondary": {
            "text_level": {kind: gc.text_level(by_kind[kind]) for kind in ic.INPUTS},
            "classifiers_given_the_user_turn": {
                "control": {c: turn["control"]["systems"][c] for c in gc.CLASSIFIERS},
                "sets": {name: {c: turn["sets"][name]["attacks"]["systems"][c] for c in gc.CLASSIFIERS}
                         for name in gc.ATTACK_SETS}},
        },
        "rows": [{k: r[k] for k in ("arm", "model", "item_id", "kind", "attack", "attacker_calls", "lg")}
                 | r["systems"] for r in rows],
    }


# ------------------------------------------------------------------------------------------------ commands
def cmd_plan() -> int:
    a = arms()
    store = TranscriptStore(STORE)
    pending = {}
    for arm in gc.ARMS:
        for model in gc.MODELS:
            recs = store.load(gc.EXPERIMENT[arm], model)
            todo = sum(1 for it in a[arm] if not ((r := recs.get((it.item_id, STORE_ARM))) and r.response is not None
                                                  and r.system_sha256 == prompt_hash(it)))
            pending[f"{arm} / {model}"] = {"to_run": todo, "projected_minutes": round(todo * SECONDS[model] / 60)}
    n = sum(len(v) for v in a.values()) * len(gc.MODELS)
    lg_done = len(_jsonl(LG_RAW))
    clf_done = len(_jsonl(CLF_RAW))
    print(json.dumps({
        "ids": len(a["plain"]), "arms": list(gc.ARMS), "models": list(gc.MODELS), "transcripts": n,
        "sealed": SEAL.is_file(),
        "classifiers_pinned": {c: bool(s.revision and s.weights_sha256) for c, s in ic.CLASSIFIERS.items()},
        "transcripts_pending": pending,
        "classifier_records": {"recorded": clf_done, "expected": len(texts(a)) * len(gc.CLASSIFIERS)},
        "llama_guard": {"recorded": lg_done, "to_run": n - lg_done,
                        "projected_minutes": round((n - lg_done) * SECONDS[LG_MODEL] / 60)},
        "scored": OUT.is_file()}, indent=1))
    return 0


def _unpinned() -> list[str]:
    return [c for c in gc.CLASSIFIERS if not (ic.CLASSIFIERS[c].revision and ic.CLASSIFIERS[c].weights_sha256)]


def cmd_seal() -> int:
    if SEAL.exists():
        raise SystemExit(f"{_rel(SEAL)} exists: the items are sealed once")
    if _unpinned():
        raise SystemExit(f"not pinned to a revision and a weights hash yet: {', '.join(_unpinned())}")
    a = arms()
    rows = gc.seal_rows(a)
    write_seal(SEAL, compute_seal(rows), meta={
        "study": "guard vs injection detectors", "ids": len(a["plain"]), "arms": list(gc.ARMS),
        "models": list(gc.MODELS), "salt": gc.SALT, "guardrail_git_sha": GUARD_SHA,
        "classifiers": {c: {"repo": s.repo, "revision": s.revision, "weights_sha256": s.weights_sha256}
                        for c, s in ic.CLASSIFIERS.items()}})
    print(json.dumps({"seal": _rel(SEAL), "rows": len(rows)}))
    return 0


def _free_ollama(model: str, force: bool):
    """(transport, the model's installed digest), once Ollama is up, has the model and runs nothing else."""
    lg3 = _lg3()
    transport = lg3.http_transport(lg3.OLLAMA)
    try:
        others = lg3.other_models(transport, model)
    except OSError as exc:
        raise SystemExit(f"Ollama is not reachable at {lg3.OLLAMA}: {exc}") from exc
    if others and not force:
        raise SystemExit(f"Ollama has another model loaded ({', '.join(others)}): one Ollama job at a time")
    digest = lg3.installed_digest(transport, model)
    if not digest:
        raise SystemExit(f"{model} is not installed in Ollama")
    return lg3, transport, digest


def _record_digest(model: str, digest: str) -> None:
    known = json.loads(MODELS_FILE.read_text(encoding="utf-8")) if MODELS_FILE.is_file() else {}
    if known.get(model, digest) != digest:
        raise SystemExit(f"{model} now has digest {digest}, but this study's transcripts were started on "
                         f"{known[model]}: every arm must come from one set of weights")
    known[model] = digest
    DIR.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(json.dumps(dict(sorted(known.items())), indent=1) + "\n", encoding="utf-8", newline="\n")


def cmd_transcripts(arm: str, model: str, force: bool, stop_after: int | None) -> int:
    if model not in gc.MODELS:
        raise SystemExit(f"--model {model!r} is refused: the registered models are {', '.join(gc.MODELS)}")
    a, _ = sealed_arms()
    _, _, digest = _free_ollama(model, force)
    _record_digest(model, digest)
    from fusion_first.model.providers.ollama import OllamaModelClient

    counts = asyncio.run(generate(
        [(model, it, STORE_ARM) for it in a[arm]],
        lambda m: OllamaModelClient(model=m, num_ctx=NUM_CTX, timeout=600), TranscriptStore(STORE),
        max_tokens=MAX_TOKENS, seed=SEED, on_progress=lambda s: print(s, flush=True), stop_after=stop_after))
    print(json.dumps({"arm": arm, "model": model, **counts}))
    return 0 if not counts["errored"] else 1


def cmd_classify() -> int:
    if _unpinned():
        raise SystemExit(f"not pinned to a revision and a weights hash yet: {', '.join(_unpinned())}")
    a, _ = sealed_arms()
    todo_texts = texts(a)
    done = {(r["classifier"], r["id"], r["input"]) for r in _jsonl(CLF_RAW)}
    for name in gc.CLASSIFIERS:
        todo = [(key, text) for key, text in todo_texts.items() if (name, *key) not in done]
        if not todo:
            continue
        loaded = ic.load(ic.CLASSIFIERS[name])
        for k, ((uid, kind), text) in enumerate(todo, 1):
            _append(CLF_RAW, ic.record(loaded, uid, kind, text))
            if k % 50 == 0 or k == len(todo):
                print(f"{name}: {k}/{len(todo)}", flush=True)
    print(json.dumps({"raw": _rel(CLF_RAW), "recorded": len(_jsonl(CLF_RAW))}))
    return 0


def cmd_llama_guard(model: str, force: bool) -> int:
    if model != LG_MODEL:
        raise SystemExit(f"--model {model!r} is refused: the registered model is {LG_MODEL!r}")
    a, _ = sealed_arms()
    try:
        replies = responses(a, TranscriptStore(STORE))
    except ValueError as exc:
        raise SystemExit(f"llama-guard: {exc} (every transcript comes first)") from exc
    lg3, transport, digest = _free_ollama(model, force)
    items = {(arm, it.item_id): it for arm in gc.ARMS for it in a[arm]}
    done = {(r["arm"], r["model"], r["item_id"]) for r in _jsonl(LG_RAW)}
    todo = [k for k in sorted(replies) if k not in done]
    for i, key in enumerate(todo, 1):
        arm, target, rid = key
        prompt = configured_prompt(items[(arm, rid)], replies[key])
        output, seconds = lg3._timed(transport, model, prompt)
        rec = {"arm": arm, "model": target, "item_id": rid, "lg_model": model, "model_digest": digest,
               "prompt_sha256": _sha(prompt), "output": output, "verdict": parse_verdict(output)["label"],
               "seconds": round(seconds, 3)}
        _append(LG_RAW, rec)
        print(f"{i}/{len(todo)} {arm} {target} {rid}: {rec['verdict']} ({seconds:.1f} s)", flush=True)
    print(json.dumps({"raw": _rel(LG_RAW), "new": len(todo), "recorded": len(done) + len(todo)}))
    return 0


def cmd_score() -> int:
    if OUT.exists():
        raise SystemExit(f"{_rel(OUT)} exists: the registered transcripts are scored once")
    store = TranscriptStore(STORE)
    files = [_rel(store.path(gc.EXPERIMENT[arm], m)) for arm in gc.ARMS for m in gc.MODELS]
    if _git("status", "--porcelain", "--", *PINNED, _rel(SEAL), _rel(MODELS_FILE), _rel(CLF_RAW), _rel(LG_RAW), *files):
        raise SystemExit("the rules, the items, the seal, the transcripts, the raw records or the scorer are modified "
                         "in the working tree: commit them first")
    rules = _git("log", "-1", "--format=%H", "--", *RULE_PATHS)
    if rules != GUARD_SHA:
        raise SystemExit(f"{RULE_PATHS} are at {rules}, not the registered {GUARD_SHA}")
    a, digest = sealed_arms()
    models = json.loads(MODELS_FILE.read_text(encoding="utf-8")) if MODELS_FILE.is_file() else {}
    if set(models) != set(gc.MODELS):
        raise SystemExit(f"{_rel(MODELS_FILE)} names {sorted(models)}, not the registered {sorted(gc.MODELS)}")
    try:
        doc = evidence(a, responses(a, store), _jsonl(LG_RAW), _jsonl(CLF_RAW), digest=digest, models=models,
                       dev_tools=dev_attacker_tools())
    except ValueError as exc:
        raise SystemExit(f"score: {exc}") from exc
    head = ("demonstration", "kind", "preregistration")
    doc = {**{k: doc[k] for k in head}, "measured": _dt.date.today().isoformat(), "git_sha": _git("rev-parse", "HEAD"),
           "guardrail_git_sha": rules, **{k: v for k, v in doc.items() if k not in head}}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for name in gc.ATTACK_SETS:
        s = doc["sets"][name]
        line = ", ".join(f"{x} {s['attacks']['systems'][x]['k']}" for x in gc.SYSTEMS)
        print(f"{name}: {s['attacks']['n']} successful attacks; stopped: {line}; verdicts: {doc['decision'][name]}")
    c = doc["control"]
    print(f"control: {c['n']} transcripts; blocked or flagged: "
          + ", ".join(f"{x} {c['systems'][x]['k']}" for x in gc.SYSTEMS))
    return 0


# ------------------------------------------------------------------------------------------------ development
def cmd_dev() -> int:
    """Development pass on SPENT rows only: the classifiers on the 310 spent InjecAgent ids' texts (plain, enhanced,
    benign twin) and, with Fusion's guard, on the transcripts steps 2 and 3 already scored. Nothing is tuned on it;
    it exercises the pipeline and sizes the study. Classifiers not pinned yet are listed as absent."""
    base = {r["id"]: r for r in gc.experiments._load("injecagent")}
    enhanced = {r["base_id"]: r for r in gc.experiments._load("injecagent_enhanced")}
    samples = {"step2": build_items("injecagent", 100, salt="fusion-evidence-step2-v1", exclude=gc.experiments.SPENT),
               "step3": build_items("injecagent", 150, salt="fusion-evidence-step3-v1", exclude=SPENT_THROUGH_STEP2)}
    spent = {it.item_id for spec in SPENT_THROUGH_STEP3
             for it in build_items("injecagent", spec[1], salt=spec[0], exclude=spec[2] if len(spec) > 2 else None)}
    twins = {r["id"].rsplit(":", 1)[0]: r["text"]
             for r in _jsonl(ROOT / "datasets/detector/v1/dev.jsonl") if r["id"].endswith(":neg")
             and r["id"].startswith("injecagent:")}
    text_of = {"plain": {i: base[i]["tool_response"] for i in sorted(spent)},
               "enhanced": {i: enhanced[i]["tool_response"] for i in sorted(spent)},
               "control": {i: twins[i] for i in sorted(spent) if i in twins}}
    flags: dict = {}
    absent = _unpinned()
    for name in gc.CLASSIFIERS:
        if name in absent:
            continue
        loaded = ic.load(ic.CLASSIFIERS[name])
        flags[name] = {arm: {i: ic.classify(loaded, t)["flagged"] for i, t in by_id.items()}
                       for arm, by_id in text_of.items()}
        print(f"{name}: " + ", ".join(f"{arm} {sum(v.values())}/{len(v)}" for arm, v in flags[name].items()),
              flush=True)
    store = TranscriptStore(STORE)
    rows = []
    for step, items in samples.items():
        for model in gc.MODELS:
            recs = store.load("injecagent", model)
            for it in items:
                rec = recs.get((it.item_id, STORE_ARM))
                if rec is None or rec.response is None:
                    raise SystemExit(f"dev: missing spent transcript {model} {it.item_id}")
                o = injecagent_outcome(it, rec.response, harness=gc.HARNESS)
                rows.append({"step": step, "model": model, "item_id": it.item_id, "attack": bool(o["attack"]),
                             "systems": {gc.REFERENCE: bool(o["stopped"]) if o["attack"] else bool(o["blocked_any"]),
                                         **{c: flags[c]["plain"][it.item_id] for c in flags}}})
    attacks = [r for r in rows if r["attack"]]
    doc = {
        "development": True,
        "note": "SPENT rows only (the ids of steps 1 to 3 and the transcripts steps 2 and 3 scored). Nothing was "
                "tuned on these numbers: the classifiers' input, windows and threshold were fixed in code first.",
        "git_sha": _git("rev-parse", "HEAD"), "measured": _dt.date.today().isoformat(),
        "classifiers": {c: {"repo": ic.CLASSIFIERS[c].repo, "revision": ic.CLASSIFIERS[c].revision} for c in flags},
        "absent_classifiers": absent,
        "text_level": {"ids": len(spent), **gc.text_level(flags)},
        "spent_transcripts": {
            "transcripts": len(rows), "attacks": len(attacks),
            "attack_rate": gc.rate(len(attacks), len(rows)),
            "stopped": {s: gc.summarize(attacks, s) for s in (gc.REFERENCE, *flags)},
            "comparisons": {c: {"attacks": gc.paired(attacks, gc.REFERENCE, c),
                                "items": gc.paired(gc.by_item(attacks), gc.REFERENCE, c)} for c in flags}},
    }
    DIR.mkdir(parents=True, exist_ok=True)
    DEV.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: doc[k] for k in ("absent_classifiers", "text_level")}, indent=1))
    print(json.dumps(doc["spent_transcripts"]["stopped"], indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guard_vs_detectors", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "dev", "seal", "classify", "score"):
        sub.add_parser(name)
    t = sub.add_parser("transcripts")
    t.add_argument("--arm", choices=gc.ARMS, required=True)
    t.add_argument("--model", required=True)
    t.add_argument("--stop-after", type=int, default=None, help="generate at most this many (smoke)")
    t.add_argument("--force", action="store_true", help="run although Ollama has another model loaded")
    lg = sub.add_parser("llama-guard")
    lg.add_argument("--model", default=LG_MODEL)
    lg.add_argument("--force", action="store_true", help="run although Ollama has another model loaded")
    a = p.parse_args(argv)
    if a.cmd == "transcripts":
        return cmd_transcripts(a.arm, a.model, a.force, a.stop_after)
    if a.cmd == "llama-guard":
        return cmd_llama_guard(a.model, a.force)
    return {"plan": cmd_plan, "dev": cmd_dev, "seal": cmd_seal, "classify": cmd_classify, "score": cmd_score}[a.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
