"""Score the detector study's confirmatory rows, once (dev-only; CPU; offline; PREREG_detector_v1.md "Scoring once").

    python scripts/detector_score.py --check-seal      # exit 0 when confirmatory.jsonl matches its seal, else 1
    python scripts/detector_score.py score [--force]

`--check-seal` prints the changed, missing and added ids (and any row outside the confirmatory split).

`score` refuses unless the seal verifies and `evals/validation/v1/detector/dev_loso.json` exists, then scores every
arm on the sealed rows with the dev-chosen decisions:
- `b0_always_negative`, `b1_phrase_list` (the raw tool result): their native binary decision (threshold 1.0);
- `embed`: each source scored by the fold model trained without it (`<models>/holdout_<source>`; blind negatives by
  `holdout_blind`) at that fold's threshold (1% FPR on the training sources' dev negatives, from dev_loso.json);
- `embed_all`: the shipped all-sources model (`<models>/all`) at its own dev threshold;
- `llama_guard3_configured`, `llama_guard3_default`: Llama Guard 3's recorded replies (lg3_raw.jsonl, from
  scripts/detector_lg3.py) on the subsample rows they cover (unscored elsewhere); absent, and said so, without any.
A fold model whose saved threshold differs from dev_loso.json is refused (it is not the model the threshold was chosen
for). The optional fine-tune (F) and ProtectAI (B3) arms are listed as absent. Latency per decision (all chunks of a
text) is measured on this CPU for b1 and embed_all; Llama Guard's is its recorded wall time.

It writes `scores.jsonl` (one line per row x arm: id, arm, score, flagged) and `detector_v1.json` (demonstration
false; the decision from `prereg.detector_decision`). An existing `detector_v1.json` is never replaced without
--force: the confirmatory rows are scored once, and a forced re-run records the file it replaced under `previous`.
Relative paths resolve from the repository root; the real embedder (bge-small, local files only) caches vectors in
a per-model subdirectory of `--cache`.
"""

from __future__ import annotations

import os

os.environ["HF_HUB_OFFLINE"] = "1"  # before anything can import transformers
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import argparse  # noqa: E402
import datetime as _dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.validate import detector_confirmatory as dc  # noqa: E402
from fusion_first.validate import detector_systems as ds  # noqa: E402
from fusion_first.validate.detector_data import (  # noqa: E402
    FRAME,
    logical_path,
    read_jsonl,
    render_frame,
)
from fusion_first.validate.llama_guard import MODEL as LG3_MODEL  # noqa: E402

SCHEMA = "dev_loso/v1"
MODELS = ".fusion/detector-models"
CACHE = ".fusion/detector-cache"  # a root: the real embedder's vectors go to ds.embedding_cache_dir under it


def _path(p: str) -> pathlib.Path:
    path = pathlib.Path(p)
    return path if path.is_absolute() else ROOT / path


def _git_sha() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file(path: pathlib.Path) -> dict:
    return {"path": logical_path(path), "sha256": _sha256(path.read_bytes())}


def _fingerprint(directory: pathlib.Path) -> str:
    """sha256 over a saved model's coefficients and meta.json (the models themselves are not committed)."""
    return _sha256((directory / "coef.npy").read_bytes() + (directory / "meta.json").read_bytes())


def _baseline_threshold(loso: dict, key: str) -> float:
    arm = loso["arms"].get(key)
    t = dc.NATIVE_THRESHOLD if arm is None else float(arm["all"]["threshold"])
    if t != dc.NATIVE_THRESHOLD:
        raise ValueError(f"dev_loso.json arms.{key}: a baseline keeps its native binary decision (threshold "
                         f"{dc.NATIVE_THRESHOLD}), not {t}")
    return t


def _load(directory: pathlib.Path, embed, tokenizer, embedder: str, threshold: float) -> ds.EmbeddingLogistic:
    """A saved model, refused unless it was trained with this embedder and carries dev_loso.json's threshold."""
    meta_path = directory / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"no saved model at {directory}")
    trained_with = json.loads(meta_path.read_text(encoding="utf-8")).get("embedder")
    if trained_with != embedder:
        raise ValueError(f"{directory} was trained with embedder {trained_with!r}, not {embedder!r}")
    model = ds.EmbeddingLogistic.load(directory, embed_fn=embed, tokenizer=tokenizer, embedder_name=embedder)
    if model.threshold != threshold:
        raise ValueError(f"{directory} carries threshold {model.threshold!r}, dev_loso.json {threshold!r}: it is not "
                         "the model dev_loso.json chose that threshold for")
    return model


def collect(rows: list[dict], loso: dict, models: pathlib.Path, embed, timer_embed, tokenizer, embedder: str,
            subsample_path: pathlib.Path, raw_path: pathlib.Path, digest: str) -> tuple[dict, dict, dict]:
    """(arm inputs for dc.build_envelope, absent arms with the reason, input fingerprints)."""
    ids = [r["id"] for r in rows]
    by_id = {r["id"]: r for r in rows}
    frames = {r["id"]: render_frame(r) for r in rows}
    arms: dict[str, dict] = {}
    absent: dict[str, str] = {}
    fingerprints: dict[str, str] = {}

    t0, t1 = _baseline_threshold(loso, "b0"), _baseline_threshold(loso, "b1")
    arms["b0_always_negative"] = {
        "scores": {r["id"]: ds.always_negative_score(r["text"]) for r in rows}, "thresholds": dict.fromkeys(ids, t0),
        "label": "B0 always-negative", "threshold": t0, "threshold_rule": dc.NATIVE_RULE, "note": "never flags"}
    arms["b1_phrase_list"] = {
        "scores": {r["id"]: ds.phrase_list_score(r["text"]) for r in rows}, "thresholds": dict.fromkeys(ids, t1),
        "label": "B1 shipped phrase list over normalized views (raw text)", "threshold": t1,
        "threshold_rule": dc.NATIVE_RULE, "latency_ms": ds.latency_ms(ds.phrase_list_score, [r["text"] for r in rows]),
        "note": "flags exactly when guard_input's phrase list matches the raw tool result or a normalized view"}

    if "embed" not in loso["arms"]:
        raise ValueError("dev_loso.json has no embed arm: train it first (scripts/detector_train.py --arm embed)")
    embed_arm = loso["arms"]["embed"]
    scores, thresholds, fold_thresholds, folds = {}, {}, {}, {}
    for source in sorted({r["source"] for r in rows}):
        fold = embed_arm["folds"].get(source)
        if fold is None:
            raise ValueError(f"dev_loso.json has no fold holding out {source}")
        t = float(fold["threshold"])
        directory = models / f"holdout_{source}"
        model = _load(directory, embed, tokenizer, embedder, t)
        mine = [r["id"] for r in rows if r["source"] == source]
        scores.update(zip(mine, model.scores([frames[i] for i in mine]), strict=True))
        thresholds.update(dict.fromkeys(mine, t))
        fold_thresholds[source], folds[source] = dc.threshold_json(t), directory.name
        fingerprints[directory.name] = _fingerprint(directory)
    arms[dc.LOSO_ARM] = {
        "scores": scores, "thresholds": thresholds,
        "label": f"E embedding ({embedder}, frozen) + balanced logistic regression, leave-one-source-out",
        "threshold": None, "threshold_rule": dc.FPR_RULE, "fold_thresholds": fold_thresholds, "folds": folds,
        "note": "each source scored by the fold model trained without it (blind negatives by holdout_blind), at "
                "that fold's threshold; pooled AUROC ranks scores from different folds; latency as embed_all"}

    t_all = float(embed_arm["all"]["threshold"])
    shipped = _load(models / "all", embed, tokenizer, embedder, t_all)
    timer = _load(models / "all", timer_embed, tokenizer, embedder, t_all)  # no cache: every timed text is embedded
    fingerprints["all"] = _fingerprint(models / "all")
    arms[dc.SHIPPED_ARM] = {
        "scores": dict(zip(ids, shipped.scores([frames[i] for i in ids]), strict=True)),
        "thresholds": dict.fromkeys(ids, t_all),
        "label": f"E shipped all-sources model ({embedder}, frozen) + balanced logistic regression",
        "threshold": t_all, "threshold_rule": dc.FPR_RULE + " (all dev negatives)", "model": "all",
        "latency_ms": ds.latency_ms(lambda f: timer.scores([f]), [frames[i] for i in ids]),
        "note": f"the shipped model (tag {dc.DETECTOR_SHIPPED_ARM!r} in primary.shipped_fpr); trained on every "
                "dev source, so its InjecAgent number is in-source and never primary"}

    if "finetune" in loso["arms"]:
        raise ValueError("dev_loso.json has a fine-tune arm, but this scorer has no fine-tune loader: add one (with "
                         "tests) before the confirmatory pass, or drop the arm (dropping F is not a protocol change)")
    absent["finetune"] = "optional arm F was not trained (dropping it is not a protocol change)"
    absent["protectai_deberta"] = ("optional arm B3 was not run: its model download needs the owner's approval "
                                   "(absent, and said so, per the registration)")

    records = read_jsonl(raw_path) if raw_path.is_file() else []
    unknown = sorted({str(r.get("arm")) for r in records} - set(dc.LG3_ARMS))
    if unknown:
        raise ValueError(f"{raw_path} holds replies for unknown arm(s): {', '.join(unknown)}")
    subsample = dc.load_subsample(subsample_path, by_id, digest) if records else []
    labels = {"configured": "B2 Llama Guard 3 8B, configured (Meta's 14 categories + S16 prompt injection)",
              "default": "B2 Llama Guard 3 8B, off-the-shelf (Meta's 14 categories)"}
    for arm, name in dc.LG3_ARMS.items():
        got = dc.lg3_arm(records, arm, subsample, by_id) if records else None
        if got is None:
            absent[name] = f"no Llama Guard 3 replies recorded (scripts/detector_lg3.py run --arm {arm})"
            continue
        arms[name] = {
            "ids": got["ids"], "scores": got["scores"], "thresholds": dict.fromkeys(got["ids"], dc.NATIVE_THRESHOLD),
            "label": labels[arm], "threshold": dc.NATIVE_THRESHOLD, "threshold_rule": dc.NATIVE_RULE,
            "latency_ms": got["latency_ms"], "model": LG3_MODEL, "model_digest": got["model_digest"],
            "subsample_n": len(subsample), "missing": got["missing"], "unparseable": got["unparseable"],
            "note": "its own stratified confirmatory subsample (the first rows of it for a partial run); the tool "
                    "result in the User turn; an 'unsafe' first line flags; an unparseable or missing reply is "
                    "unscored; latency is Ollama's wall time per reply"}
    inputs = {"lg3_subsample": _file(subsample_path) if records else None,
              "lg3_raw": _file(raw_path) if records else None, "models": fingerprints}
    return arms, absent, inputs


def cmd_check_seal(a) -> int:
    try:
        diff = dc.seal_diff(_path(a.data), _path(a.seal))
    except (FileNotFoundError, ValueError) as e:
        print(f"check-seal: {e}", file=sys.stderr)
        return 1
    clean = not any(diff.values())
    print(json.dumps({"clean": clean, **diff}, indent=1))
    return 0 if clean else 1


def cmd_score(a, embed_fn, tokenizer) -> int:
    out, scores_path = _path(a.out), _path(a.scores)
    previous = None
    if out.exists():
        if not a.force:
            raise FileExistsError(f"{out} exists: the confirmatory rows are scored once, and a re-run must be an "
                                  "explicit, logged act (pass --force)")
        prior = out.read_bytes()
        doc = json.loads(prior)
        previous = {"sha256": _sha256(prior), "measured": doc.get("measured"), "git_sha": doc.get("git_sha"),
                    "adopt": (doc.get("decision") or {}).get("adopt")}
        print(f"score: --force: replacing {out} (sha256 {previous['sha256']}); recorded under 'previous'",
              file=sys.stderr)
    loso_path = _path(a.dev_loso)
    if not loso_path.is_file():
        raise FileNotFoundError(f"no dev thresholds at {loso_path}: run scripts/detector_train.py first")
    loso = json.loads(loso_path.read_text(encoding="utf-8"))
    if loso.get("schema") != SCHEMA:
        raise ValueError(f"{loso_path} has schema {loso.get('schema')!r}, not {SCHEMA!r}")
    rows, digest = dc.sealed_rows(_path(a.data), _path(a.seal))

    if (embed_fn is None) != (tokenizer is None):
        raise ValueError("inject embed_fn together with its tokenizer; with neither, the local bge-small is loaded")
    if embed_fn is None:
        embed_fn, tokenizer = ds.bge_embedder(seed=ds.SEED)
        embedder = ds.EMBED_MODEL
        cache = ds.embedding_cache_dir(embedder, ds.MAX_TOKENS, root=_path(a.cache or CACHE))
    else:
        embedder = ds.INJECTED
        cache = ds.embedding_cache_dir(embedder, ds.MAX_TOKENS, root=_path(a.cache)) if a.cache else None
    ds.seed_everything(ds.SEED)
    arms, absent, inputs = collect(rows, loso, _path(a.models), ds.CachedEmbedder(embed_fn, cache), embed_fn,
                                   tokenizer, embedder, _path(a.subsample), _path(a.lg3_raw), digest)
    meta = {"measured": _dt.date.today().isoformat(), "git_sha": _git_sha(), "frame": FRAME,
            "inputs": {"data": logical_path(_path(a.data)), "seal": logical_path(_path(a.seal)),
                       "dev_loso": {**_file(loso_path), "git_sha": loso.get("git_sha"), "built": loso.get("built")},
                       "embedder": embedder, **inputs}}
    if previous:
        meta["previous"] = previous
    envelope, lines = dc.build_envelope(rows, arms, digest=digest, absent=absent, meta=meta)
    body = "".join(json.dumps(x, allow_nan=False) + "\n" for x in lines).encode("utf-8")
    envelope["inputs"]["scores"] = {"path": logical_path(scores_path), "sha256": _sha256(body)}
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    scores_path.write_bytes(body)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(envelope, indent=1, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    p = envelope["primary"]
    print(json.dumps({"out": str(out), "adopt": envelope["decision"]["adopt"],
                      "injecagent_recall": [p["injecagent_recall"][k] for k in ("point", "n")],
                      "shipped_fpr": [p["shipped_fpr"][k] for k in ("point", "n")],
                      "arms": sorted(envelope["arms"]), "absent": sorted(absent)}))
    return 0


def main(argv: list[str] | None = None, *, embed_fn=None, tokenizer=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["score"], help="score the confirmatory rows (once)")
    ap.add_argument("--check-seal", action="store_true", help="verify confirmatory.jsonl against its seal")
    ap.add_argument("--force", action="store_true", help="replace an existing detector_v1.json (logged)")
    ap.add_argument("--data", default=dc.DATA)
    ap.add_argument("--seal", default=dc.SEAL)
    ap.add_argument("--dev-loso", default=dc.DEV_LOSO)
    ap.add_argument("--models", default=MODELS)
    ap.add_argument("--subsample", default=dc.SUBSAMPLE)
    ap.add_argument("--lg3-raw", default=dc.LG3_RAW)
    ap.add_argument("--scores", default=dc.SCORES)
    ap.add_argument("--out", default=dc.EVIDENCE)
    ap.add_argument("--cache", default=None,
                    help=f"embedding cache root (default {CACHE} for the real embedder; per-model subdirectory)")
    a = ap.parse_args(argv)
    if a.check_seal == (a.cmd == "score"):
        ap.error("give exactly one of --check-seal or score")
    if a.check_seal:
        return cmd_check_seal(a)
    try:
        return cmd_score(a, embed_fn, tokenizer)
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        print(f"score: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
