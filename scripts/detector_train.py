"""Leave-one-source-out readout of the tool-result injection detector on the DEV split (dev-only; CPU; offline).

    python scripts/detector_train.py --arm embed --loso [--data datasets/detector/v1/dev.jsonl]
        [--out evals/validation/v1/detector/dev_loso.json] [--models .fusion/detector-models]
        [--cache .fusion/detector-cache]
    python scripts/detector_train.py --arm b0 --loso      # always-negative
    python scripts/detector_train.py --arm b1 --loso      # the shipped phrase list (raw text)
    python scripts/detector_train.py --arm finetune --holdout {injecagent,agentdojo,all}
        [--epochs 3] [--batch-size 16] [--lr 3e-5] [--max-len 256] [--smoke N]

One fold per source present in the dev file. For each held-out source the embed arm trains on the other sources'
dev rows (chunk labels per PREREG "Long texts"; a long positive without a reliable span is left out of training and
counted per source in `excluded_unreliable_span_positives`), fixes the threshold at 1% false-positive rate on those
training sources' dev negatives (`operating_threshold_at_fpr`; threshold_rule "fpr_0.01_on_training_dev_negatives"),
scores every held-out row text-level (max over chunks) and saves the fold model to `<models>/holdout_<source>/`; it
also trains the all-sources model on every dev row (threshold at 1% FPR on all dev negatives) and saves it to
`<models>/all/`. The baselines train nothing and keep their native binary decision (PREREG "Operating points";
threshold_rule "native_binary": flag on a score of 1.0, a phrase-list match; always-negative never flags): the FPR
rule is never applied to them.

The optional fine-tune arm F (PREREG: two named folds, hold out InjecAgent and hold out AgentDojo, plus the
all-sources model) runs one fold per invocation because each takes long on CPU: `--holdout <source>` trains
bge-small with a 2-label head (`detector_finetune.FineTunedClassifier`) on the other sources' dev rows (the same chunk
labels as the embed arm), fixes the threshold at 1% FPR on those training sources' dev negatives, scores every
held-out row text-level (max over chunks) and saves to `<models>/finetune_holdout_<source>/`; `--holdout all` trains
on every dev row and saves to `<models>/finetune_all/`. A run adds or replaces only its own fold (or `all`) in
`arms.finetune` and keeps the rest; folds built from another dev file (another data_sha256) are dropped. F is not a
full LOSO, so its `pooled_auroc` is null: compare it per fold. `--epochs/--batch-size/--lr/--max-len` override the
defaults and are recorded in meta.json and the fold block; the window follows `--max-len` (`max_len` tokens, stride
`max_len // 2`), so only the default 256 is the registered window. `--smoke N` trains on the first N training rows
of the fold for timing only: it prints the seconds and a projected full-fold time and writes nothing.

The JSON (schema "dev_loso/v1"): {schema, demonstration: true, diagnostic: true, note, git_sha, built, seed,
fpr_target, arms: {<arm>: {label, threshold_rule, folds: {<source>: rates + auroc + threshold + n_train},
pooled_auroc, all: {threshold, ...}, ...}}}. A run rewrites its own arm (the fine-tune arm: its own fold) and keeps
the other arms of a file with the same schema. Everything there is DIAGNOSTIC and never quoted. Relative paths resolve
from the repository root, never the working directory; the real embedder caches its vectors in a per-model
subdirectory of `--cache`.

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
import time  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fusion_first.schemas import Interval  # noqa: E402
from fusion_first.validate import detector_finetune as ft  # noqa: E402
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
CHUNK_LABELS = ("PREREG Long texts: positive when the chunk contains the whole span; when none does: inside it, "
                "at least half the chunk's tokens over it, or holding at least half the span's tokens")
FINETUNE_HOLDOUTS = ("injecagent", "agentdojo", "all")  # PREREG arm F: two named folds, plus the all-sources model
FINETUNE_POOLED_NOTE = ("arm F runs named folds only (PREREG: hold out InjecAgent; hold out AgentDojo), not a full "
                        "LOSO: compare it per fold")


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
                         "training_labels": CHUNK_LABELS},
            # per source, over every dev row: excluded from each fold that trains on that source and from `all`
            "excluded_unreliable_span_positives": _per_source(rows, ex_all.excluded, sources),
            "positives_without_a_positive_chunk": _per_source(rows, ex_all.uncovered, sources),
            "folds": table, "pooled_auroc": pooled,
            "all": {"threshold": everything.threshold, "n_train": len(rows),
                    "n_train_examples": everything.n_train, "n_train_excluded": len(ex_all.excluded)}}


# ---------------------------------------------------------------- arm F (optional fine-tune)


def _ft_training_rows(rows: list[dict], held: str) -> list[dict]:
    return rows if held == "all" else [r for r in rows if r["source"] != held]


def finetune_block(rows: list[dict], held: str, models_dir: pathlib.Path, clf: ft.FineTunedClassifier,
                   hp: dict) -> dict:
    """Arm F for one fold (or `all`): train without the held-out source (or on every dev row), fix the threshold at
    1% FPR on the training sources' dev negatives, save the model and, for a fold, score every held-out row
    text-level (max over chunks). Returns the fold block (embed's fold shape) or the `all` block."""
    train = _ft_training_rows(rows, held)
    max_tokens, stride = ft.window(hp["max_len"])
    ex = ds.training_examples(train, clf.tokenizer, max_tokens, stride)
    start = time.perf_counter()
    clf.fit(ex.texts, ex.labels, **hp)
    clf.threshold = operating_threshold_at_fpr(clf.scores([render_frame(r) for r in train if not r["label"]]), FPR)
    name = "finetune_all" if held == "all" else f"finetune_holdout_{held}"
    clf.save(models_dir / name)
    block = {"threshold": clf.threshold, "n_train": len(train), "n_train_examples": clf.n_train,
             "n_train_excluded": len(ex.excluded), "positives_without_a_positive_chunk": len(ex.uncovered),
             "backbone": clf.backbone_name, "hyperparameters": dict(hp),
             "window": {"max_tokens": max_tokens, "stride": stride}, "model": name}
    if held != "all":
        held_rows = [r for r in rows if r["source"] == held]  # every held-out row is scored, excluded or not
        scores = dict(zip([r["id"] for r in held_rows], clf.scores([render_frame(r) for r in held_rows]),
                          strict=True))
        table = loso_table({held: {"rows": rows, "scores": scores, "threshold": clf.threshold}})
        block = _fold_entry(table, held, rows, scores, **block)
    block["seconds"] = time.perf_counter() - start  # training, threshold and held-out scoring
    return block


def merge_finetune(prior: dict | None, held: str, block: dict, data_sha256: str, backbone: str) -> dict:
    """`arms.finetune` with this run's fold (or `all`) added or replaced and the rest of a prior arm kept, unless
    that arm was built from another dev file."""
    if prior and prior.get("data_sha256") != data_sha256:
        print("arm finetune in the readout was built from another dev file (data_sha256 differs); its folds are "
              "dropped", file=sys.stderr)
        prior = None
    folds = dict((prior or {}).get("folds", {}))
    everything = (prior or {}).get("all", {"threshold": None})
    if held == "all":
        everything = block
    else:
        folds[held] = block
    return {"label": f"F fine-tuned {backbone} (2-label classification head, end to end)",
            "threshold_rule": FPR_RULE,
            "chunking": {"registered_window": {"max_tokens": ds.MAX_TOKENS, "stride": ds.STRIDE},
                         "window": "max_len tokens, stride max_len // 2 (see each block's window)",
                         "text_score": "max over chunks", "training_labels": CHUNK_LABELS},
            "folds": dict(sorted(folds.items())), "pooled_auroc": None, "pooled_auroc_note": FINETUNE_POOLED_NOTE,
            "all": everything}


def finetune_smoke(rows: list[dict], held: str, n: int, clf: ft.FineTunedClassifier, hp: dict) -> dict:
    """Time arm F on the first `n` training rows of the fold and project the full fold by token counts (training
    examples for the fit; chunks of the training negatives and held-out rows for the scoring). Writes nothing."""
    train = _ft_training_rows(rows, held)
    sample = train[:n]
    max_tokens, stride = ft.window(hp["max_len"])
    tok = clf.tokenizer
    ex = ds.training_examples(sample, tok, max_tokens, stride)
    start = time.perf_counter()
    clf.fit(ex.texts, ex.labels, **hp)
    fit_seconds = time.perf_counter() - start
    frames = [render_frame(r) for r in sample]
    start = time.perf_counter()
    clf.scores(frames)
    score_seconds = time.perf_counter() - start
    full = ds.training_examples(train, tok, max_tokens, stride)
    scored = [render_frame(r) for r in train if not r["label"]]
    scored += [] if held == "all" else [render_frame(r) for r in rows if r["source"] == held]

    def tokens(texts: list[str]) -> int:
        return sum(len(tok(t, truncation=True, max_length=hp["max_len"])["input_ids"]) for t in texts)

    def chunk_tokens(texts: list[str]) -> int:
        return tokens([c for t in texts for c in ds.chunk_frame(t, tok, max_tokens, stride)])

    projected = (fit_seconds * tokens(full.texts) / max(1, tokens(ex.texts))
                 + score_seconds * chunk_tokens(scored) / max(1, chunk_tokens(frames)))
    return {"smoke": n, "holdout": held, "rows": len(sample), "examples": len(ex.texts),
            "fit_seconds": fit_seconds, "score_seconds": score_seconds,
            "full_fold": {"rows": len(train), "examples": len(full.texts), "scored_frames": len(scored)},
            "projected_fold_seconds": projected, "projected_fold_minutes": projected / 60,
            "backbone": clf.backbone_name, "hyperparameters": dict(hp),
            "note": "timing only, nothing written; the projection scales each phase by token counts"}


def _prior(out: pathlib.Path) -> dict:
    prior = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    if prior and prior.get("schema") != SCHEMA:
        print(f"{out}: schema {prior.get('schema')!r} is not {SCHEMA!r}; its arms are not kept", file=sys.stderr)
        return {}
    return prior


def main(argv: list[str] | None = None, *, embed_fn=None, tokenizer=None, backbone=None) -> int:
    """`embed_fn` + `tokenizer` stand in for bge-small in the embed arm; `backbone` (a 2-label sequence
    classification model) + `tokenizer` stand in for it in the fine-tune arm."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["embed", "finetune", *BASELINES], required=True)
    ap.add_argument("--loso", action="store_true",
                    help="leave-one-source-out over the dev split (required for embed, b0 and b1)")
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--models", default=MODELS)
    ap.add_argument("--cache", default=None,
                    help=f"embedding cache root (default {CACHE} for the real embedder; vectors go to a "
                         "per-model subdirectory)")
    ft_group = ap.add_argument_group("fine-tune arm (--arm finetune)")
    ft_group.add_argument("--holdout", choices=FINETUNE_HOLDOUTS,
                          help="the held-out source of this run, or all for the all-sources model")
    ft_group.add_argument("--smoke", type=int, metavar="N",
                          help="train on the first N training rows for timing only; writes nothing")
    ft_group.add_argument("--epochs", type=int, help=f"default {ft.EPOCHS}")
    ft_group.add_argument("--batch-size", type=int, help=f"default {ft.BATCH_SIZE}")
    ft_group.add_argument("--lr", type=float, help=f"default {ft.LR}")
    ft_group.add_argument("--max-len", type=int,
                          help=f"default {ft.MAX_LEN} (the registered window); the window follows it")
    a = ap.parse_args(argv)

    overrides = {"epochs": a.epochs, "batch_size": a.batch_size, "lr": a.lr, "max_len": a.max_len}
    if a.arm == "finetune":
        if a.holdout is None:
            ap.error(f"--arm finetune needs --holdout {{{','.join(FINETUNE_HOLDOUTS)}}} (one fold per run)")
        if a.smoke is not None and a.smoke < 1:
            ap.error("--smoke needs N >= 1")
        if any(v is not None and v <= 0 for v in overrides.values()):
            ap.error("--epochs, --batch-size, --lr and --max-len must be positive")
        if a.max_len is not None and a.max_len < 4:
            ap.error("--max-len must leave room for the special tokens and a window")
    else:
        if not a.loso:
            ap.error(f"--arm {a.arm} needs --loso")
        if a.holdout is not None or a.smoke is not None or any(v is not None for v in overrides.values()):
            ap.error("--holdout, --smoke, --epochs, --batch-size, --lr and --max-len are for --arm finetune")

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
    if a.arm == "finetune" and a.holdout != "all" and a.holdout not in sources:
        ap.error(f"--holdout {a.holdout}: the dev file has no rows from that source")
    data_sha256 = hashlib.sha256(data.read_bytes()).hexdigest()

    ds.seed_everything(ds.SEED)
    if a.arm == "finetune":
        if (backbone is None) != (tokenizer is None):
            raise ValueError("inject the backbone together with its tokenizer; with neither, the local "
                             "bge-small and its tokenizer are loaded")
        hp = {"epochs": a.epochs or ft.EPOCHS, "batch_size": a.batch_size or ft.BATCH_SIZE, "lr": a.lr or ft.LR,
              "max_len": a.max_len or ft.MAX_LEN, "seed": ds.SEED, "threads": ft.THREADS}
        if hp["max_len"] != ft.MAX_LEN:
            print(f"--max-len {hp['max_len']}: windows of {hp['max_len']} tokens, not the registered "
                  f"{ds.MAX_TOKENS} (recorded in meta.json and the readout)", file=sys.stderr)
        clf = ft.FineTunedClassifier() if backbone is None else ft.FineTunedClassifier(backbone, tokenizer)
        if a.smoke is not None:
            print(json.dumps(finetune_smoke(rows, a.holdout, a.smoke, clf, hp)))
            return 0
        block = finetune_block(rows, a.holdout, _path(a.models), clf, hp)
    elif a.arm == "embed":
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
    out = _path(a.out)
    prior = _prior(out)
    if a.arm == "finetune":
        result = merge_finetune(prior.get("arms", {}).get(a.arm), a.holdout,
                                {**block, "git_sha": git_sha, "built": built}, data_sha256, clf.backbone_name)
    result.update(data=logical_path(data), data_sha256=data_sha256, git_sha=git_sha, built=built)
    report = {"schema": SCHEMA, "demonstration": True, "diagnostic": True, "note": NOTE, "git_sha": git_sha,
              "built": built, "seed": ds.SEED, "fpr_target": FPR,
              "arms": {**prior.get("arms", {}), a.arm: result}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_clean(report), indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    summary = {"out": str(out), "arm": a.arm, "folds": list(result["folds"]) if a.arm == "finetune" else sources,
               "pooled_auroc": _clean(result["pooled_auroc"])}
    if a.arm == "finetune":
        summary.update(holdout=a.holdout, threshold=_clean(block["threshold"]), auroc=_clean(block.get("auroc")))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
