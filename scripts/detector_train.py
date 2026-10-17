"""Leave-one-source-out readout of the tool-result injection detector on the DEV split (dev-only; CPU; offline).

    python scripts/detector_train.py --arm embed --loso [--data datasets/detector/v1/dev.jsonl]
        [--out evals/validation/v1/detector/dev_loso.json] [--models .fusion/detector-models]
    python scripts/detector_train.py --arm b0 --loso      # always-negative
    python scripts/detector_train.py --arm b1 --loso      # the shipped phrase list (raw text)

One fold per source present in the dev file. For each held-out source the embed arm trains on the other sources'
dev rows, fixes the threshold at 1% false-positive rate on those training sources' dev negatives
(`operating_threshold_at_fpr`), scores the held-out source's rows and saves the fold model to
`<models>/holdout_<source>/`; it also trains the all-sources model on every dev row (threshold at 1% FPR on all dev
negatives) and saves it to `<models>/all/`. The baselines train nothing and keep their own fixed decision (flag on a
score of 1.0: a phrase-list match; always-negative never flags). Each arm is written into the one JSON under
`arms.<arm>`, keeping the other arms. Everything there is DIAGNOSTIC and never quoted.

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

DATA = "datasets/detector/v1/dev.jsonl"
OUT = "evals/validation/v1/detector/dev_loso.json"
MODELS = ".fusion/detector-models"
CACHE = ".fusion/detector-cache"
FPR = 0.01
NOTE = "dev LOSO readout; never quote"
BASELINES = {
    "b0": ("B0 always-negative", ds.always_negative_score),
    "b1": ("B1 shipped phrase list over normalized views (raw text)", ds.phrase_list_score),
}
BASELINE_THRESHOLD = 1.0  # the baselines' own decision: a phrase match scores 1.0; always-negative never does


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
    return {"label": label, "threshold_rule": "fixed: the system's own decision (score 1.0)", "folds": table,
            "pooled_auroc": pooled}


def _train(rows: list[dict], embed, tokenizer, threshold_rows: list[dict]) -> ds.EmbeddingLogistic:
    texts, labels = ds.training_examples(rows, tokenizer)
    model = ds.EmbeddingLogistic(embed_fn=embed, tokenizer=tokenizer).fit(texts, labels)
    model.threshold = operating_threshold_at_fpr(model.scores([render_frame(r) for r in threshold_rows]), FPR)
    return model


def embed_arm(rows: list[dict], sources: list[str], models_dir: pathlib.Path, embed, tokenizer) -> dict:
    folds, meta = {}, {}
    for held in sources:
        train = [r for r in rows if r["source"] != held]
        model = _train(train, embed, tokenizer, [r for r in train if not r["label"]])
        model.save(models_dir / f"holdout_{held}")
        held_rows = [r for r in rows if r["source"] == held]
        folds[held] = {"rows": rows, "threshold": model.threshold,
                       "scores": dict(zip([r["id"] for r in held_rows],
                                          model.scores([render_frame(r) for r in held_rows]), strict=True))}
        meta[held] = {"n_train": len(train), "n_train_examples": model.n_train}
    table, pooled = _folds(rows, folds, meta)
    everything = _train(rows, embed, tokenizer, [r for r in rows if not r["label"]])
    everything.save(models_dir / "all")
    return {"label": f"E embedding ({ds.EMBED_MODEL}, frozen) + balanced logistic regression",
            "threshold_rule": f"{FPR:.0%} FPR on the training sources' dev negatives",
            "embedder": {"model": ds.EMBED_MODEL, "normalize_embeddings": True, "max_seq_length": ds.MAX_TOKENS,
                         "batch_size": ds.BATCH_SIZE},
            "chunking": {"max_tokens": ds.MAX_TOKENS, "stride": ds.STRIDE, "text_score": "max over chunks"},
            "folds": table, "pooled_auroc": pooled,
            "all": {"threshold": everything.threshold, "n_train": len(rows),
                    "n_train_examples": everything.n_train}}


def main(argv: list[str] | None = None, *, embed_fn=None, tokenizer=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["embed", *BASELINES], required=True)
    ap.add_argument("--loso", action="store_true", required=True, help="leave-one-source-out over the dev split")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--models", default=MODELS)
    ap.add_argument("--cache", default=None, help=f"embedding cache (default {CACHE} for the real embedder)")
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
        if embed_fn is None:
            embed_fn, real_tokenizer = ds.bge_embedder(seed=ds.SEED)
            tokenizer = tokenizer or real_tokenizer
            cache = _path(a.cache or CACHE)
        else:
            cache = _path(a.cache) if a.cache else None
        result = embed_arm(rows, sources, _path(a.models), ds.CachedEmbedder(embed_fn, cache), tokenizer)
    else:
        result = baseline_arm(rows, sources, a.arm)

    built = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat()
    git_sha = _git_sha()
    result.update(data=logical_path(data), data_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                  git_sha=git_sha, built=built)
    out = _path(a.out)
    report = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    report.update(demonstration=True, diagnostic=True, note=NOTE, git_sha=git_sha, built=built, seed=ds.SEED,
                  fpr_target=FPR)
    report["arms"] = {**report.get("arms", {}), a.arm: result}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_clean(report), indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(out), "arm": a.arm, "folds": sources,
                      "pooled_auroc": _clean(result["pooled_auroc"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
