"""Leave-one-source-out readout of the tool-result injection detector on the DEV split (dev-only; CPU; offline).

    python scripts/detector_train.py --arm embed --loso [--data datasets/detector/v1/dev.jsonl]
        [--out evals/validation/v1/detector/dev_loso.json] [--models .fusion/detector-models]
        [--cache .fusion/detector-cache]
    python scripts/detector_train.py --arm b0 --loso      # always-negative
    python scripts/detector_train.py --arm b1 --loso      # the shipped phrase list (raw text)

One fold per source present in the dev file. For each held-out source the embed arm trains on the other sources'
dev rows (chunk labels per PREREG "Long texts"; a long positive without a reliable span is left out of training and
counted per source in `excluded_unreliable_span_positives`), fixes the threshold at 1% false-positive rate on those
training sources' dev negatives (`operating_threshold_at_fpr`; threshold_rule "fpr_0.01_on_training_dev_negatives"),
scores every held-out row text-level (max over chunks) and saves the fold model to `<models>/holdout_<source>/`; it
also trains the all-sources model on every dev row (threshold at 1% FPR on all dev negatives) and saves it to
`<models>/all/`. The baselines train nothing and keep their native binary decision (PREREG "Operating points";
threshold_rule "native_binary": flag on a score of 1.0, a phrase-list match; always-negative never flags): the FPR
rule is never applied to them.

The JSON (schema "dev_loso/v1"): {schema, demonstration: true, diagnostic: true, note, git_sha, built, seed,
fpr_target, arms: {<arm>: {label, threshold_rule, folds: {<source>: rates + auroc + threshold + n_train},
pooled_auroc, all: {threshold, ...}, ...}}}. A run rewrites its own arm and keeps the other arms of a file with the
same schema. Everything there is DIAGNOSTIC and never quoted. Relative paths resolve from the repository root, never
the working directory; the real embedder caches its vectors in a per-model subdirectory of `--cache`.

This script never reads the confirmatory split: it refuses a path naming it and any row outside `dev`.
"""

from __future__ import annotations

import os

os.environ["HF_HUB_OFFLINE"] = "1"  # before anything can import transformers
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import argparse  # noqa: E402
import datetime as _dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.schemas import Interval  # noqa: E402
from fusion_first.validate import detector_systems as ds  # noqa: E402
from fusion_first.validate.detector_data import (  # noqa: E402
    SOURCES,
    logical_path,
    read_jsonl,
    render_frame,
)
from fusion_first.validate.detector_eval import (  # noqa: E402
    auroc,
    loso_table,
    operating_threshold_at_fpr,
)

SCHEMA = "dev_loso/v1"
DATA = "datasets/detector/v1/dev.jsonl"  # relative paths resolve from the repository root (ROOT), not the cwd
OUT = "evals/validation/v1/detector/dev_loso.json"
MODELS = ".fusion/detector-models"
CACHE = ".fusion/detector-cache"  # a root: the real embedder's vectors go to ds.embedding_cache_dir under it
FPR = 0.01
NOTE = "dev LOSO readout; never quote"
BASELINES = {
    "b0": ("B0 always-negative", ds.always_negative_score),
    "b1": ("B1 shipped phrase list over normalized views (raw text)", ds.phrase_list_score),
}
# PREREG "Operating points": the baselines keep their native binary decision (a phrase match scores 1.0;
# always-negative never does); the 1%-FPR rule is for the learned arms only.
BASELINE_THRESHOLD = 1.0
NATIVE_RULE = "native_binary"
FPR_RULE = f"fpr_{FPR}_on_training_dev_negatives"


def _git_sha() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.stdout.strip()


def _path(p: str) -> pathlib.Path:
    path = pathlib.Path(p)
    return path if path.is_absolute() else ROOT / path


def _clean(obj: object) -> object:
    """JSON-safe: Intervals as dicts, NaN as null, an infinite threshold as the string "inf"."""
    if isinstance(obj, Interval):
        return _clean(obj.model_dump())
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None if math.isnan(obj) else str(obj)
    return obj


def _fold_entry(table: dict, source: str, rows: list[dict], scores: dict[str, float], threshold: float,
                n_train: int, **extra) -> dict:
    held = [r for r in rows if r["source"] == source]
    return {**table[source], "auroc": auroc([bool(r["label"]) for r in held], [scores[r["id"]] for r in held]),
            "threshold": threshold, "n_train": n_train, **extra}


def _folds(rows: list[dict], folds: dict[str, dict], meta: dict[str, dict]) -> tuple[dict, float]:
    table = loso_table(folds)
    out = {s: _fold_entry(table, s, rows, folds[s]["scores"], folds[s]["threshold"], **meta[s]) for s in folds}
    pooled = {r["id"]: folds[r["source"]]["scores"][r["id"]] for r in rows}
    return out, auroc([bool(r["label"]) for r in rows], [pooled[r["id"]] for r in rows])


def baseline_arm(rows: list[dict], sources: list[str], arm: str) -> dict:
    label, fn = BASELINES[arm]
    scores = {r["id"]: fn(r["text"]) for r in rows}  # the baselines score the raw text
    folds = {s: {"rows": rows, "scores": scores, "threshold": BASELINE_THRESHOLD} for s in sources}
    meta = {s: {"n_train": sum(r["source"] != s for r in rows)} for s in sources}
    table, pooled = _folds(rows, folds, meta)
    return {"label": label, "threshold_rule": NATIVE_RULE, "folds": table, "pooled_auroc": pooled,
            "all": {"threshold": BASELINE_THRESHOLD}}


def _train(rows: list[dict], embed, tokenizer, threshold_rows: list[dict],
           embedder_name: str) -> tuple[ds.EmbeddingLogistic, ds.TrainingExamples]:
    ex = ds.training_examples(rows, tokenizer)
    model = ds.EmbeddingLogistic(embed_fn=embed, tokenizer=tokenizer, embedder_name=embedder_name)
    model.fit(ex.texts, ex.labels)
    model.threshold = operating_threshold_at_fpr(model.scores([render_frame(r) for r in threshold_rows]), FPR)
    return model, ex


def _per_source(rows: list[dict], ids: list[str], sources: list[str]) -> dict[str, int]:
    chosen = set(ids)
    return {s: sum(r["id"] in chosen for r in rows if r["source"] == s) for s in sources}


def embed_arm(rows: list[dict], sources: list[str], models_dir: pathlib.Path, embed, tokenizer,
              embedder_name: str = ds.INJECTED) -> dict:
    folds, meta = {}, {}
    for held in sources:
        train = [r for r in rows if r["source"] != held]
        model, ex = _train(train, embed, tokenizer, [r for r in train if not r["label"]], embedder_name)
        model.save(models_dir / f"holdout_{held}")
        held_rows = [r for r in rows if r["source"] == held]  # every held-out row is scored, excluded or not
        folds[held] = {"rows": rows, "threshold": model.threshold,
                       "scores": dict(zip([r["id"] for r in held_rows],
                                          model.scores([render_frame(r) for r in held_rows]), strict=True))}
        meta[held] = {"n_train": len(train), "n_train_examples": model.n_train,
                      "n_train_excluded": len(ex.excluded)}
    table, pooled = _folds(rows, folds, meta)
    everything, ex_all = _train(rows, embed, tokenizer, [r for r in rows if not r["label"]], embedder_name)
    everything.save(models_dir / "all")
    real = embedder_name == ds.EMBED_MODEL
    return {"label": f"E embedding ({embedder_name}, frozen) + balanced logistic regression",
            "threshold_rule": FPR_RULE,
            "embedder": {"model": embedder_name, "normalize_embeddings": True if real else None,
                         "max_seq_length": ds.MAX_TOKENS if real else None,
                         "batch_size": ds.BATCH_SIZE if real else None},
            "chunking": {"max_tokens": ds.MAX_TOKENS, "stride": ds.STRIDE, "text_score": "max over chunks",
                         "training_labels": "PREREG Long texts: positive when the chunk contains the whole span; "
                                            "when none does: inside it, at least half the chunk's tokens "
                                            "over it, or holding at least half the span's tokens"},
            # per source, over every dev row: excluded from each fold that trains on that source and from `all`
            "excluded_unreliable_span_positives": _per_source(rows, ex_all.excluded, sources),
            "positives_without_a_positive_chunk": _per_source(rows, ex_all.uncovered, sources),
            "folds": table, "pooled_auroc": pooled,
            "all": {"threshold": everything.threshold, "n_train": len(rows),
                    "n_train_examples": everything.n_train, "n_train_excluded": len(ex_all.excluded)}}


def main(argv: list[str] | None = None, *, embed_fn=None, tokenizer=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["embed", *BASELINES], required=True)
    ap.add_argument("--loso", action="store_true", required=True, help="leave-one-source-out over the dev split")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--models", default=MODELS)
    ap.add_argument("--cache", default=None,
                    help=f"embedding cache root (default {CACHE} for the real embedder; vectors go to a "
                         "per-model subdirectory)")
    a = ap.parse_args(argv)

    paths = [a.data, a.out, a.models, a.cache or ""]
    if any("confirmatory" in str(p).lower() for p in paths):
        ap.error("refusing a path that names the confirmatory split: training and LOSO read dev.jsonl only")
    data = _path(a.data)
    rows = read_jsonl(data)
    if any(r.get("split") != "dev" for r in rows):
        ap.error(f"{a.data} holds rows outside the dev split; training and LOSO read dev rows only")
    sources = [s for s in SOURCES if any(r["source"] == s for r in rows)]
    if len(sources) < 2:
        ap.error("leave-one-source-out needs rows from at least two sources")

    ds.seed_everything(ds.SEED)
    if a.arm == "embed":
        if (embed_fn is None) != (tokenizer is None):
            raise ValueError("inject embed_fn together with its tokenizer (chunking needs the embedder's own "
                             "tokenizer); with neither, the local bge-small and its tokenizer are loaded")
        if embed_fn is None:
            embed_fn, tokenizer = ds.bge_embedder(seed=ds.SEED)
            name = ds.EMBED_MODEL
            cache = ds.embedding_cache_dir(ds.EMBED_MODEL, ds.MAX_TOKENS, root=_path(a.cache or CACHE))
        else:
            name = ds.INJECTED
            cache = ds.embedding_cache_dir(name, ds.MAX_TOKENS, root=_path(a.cache)) if a.cache else None
        result = embed_arm(rows, sources, _path(a.models), ds.CachedEmbedder(embed_fn, cache), tokenizer, name)
    else:
        result = baseline_arm(rows, sources, a.arm)

    built = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat()
    git_sha = _git_sha()
    result.update(data=logical_path(data), data_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                  git_sha=git_sha, built=built)
    out = _path(a.out)
    prior = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    if prior and prior.get("schema") != SCHEMA:
        print(f"{out}: schema {prior.get('schema')!r} is not {SCHEMA!r}; its arms are not kept", file=sys.stderr)
        prior = {}
    report = {"schema": SCHEMA, "demonstration": True, "diagnostic": True, "note": NOTE, "git_sha": git_sha,
              "built": built, "seed": ds.SEED, "fpr_target": FPR,
              "arms": {**prior.get("arms", {}), a.arm: result}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_clean(report), indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(out), "arm": a.arm, "folds": sources,
                      "pooled_auroc": _clean(result["pooled_auroc"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
