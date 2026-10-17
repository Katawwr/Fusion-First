"""The detector study's confirmatory pass (dev-only; nothing here ships in the wheel): the sealed rows, the Llama
Guard 3 subsample and prompt, and the one-shot evidence envelope (PREREG_detector_v1.md "Scoring once").

`sealed_rows` (and `seal_diff`, which only reports) is the only reader of the confirmatory rows: it loads the
committed seal (its own digest checked) before it opens the rows, and refuses them unless every id and row hash
matches. Scores come in from the caller (the fold models, the shipped model, Llama Guard's recorded replies); no
model is called here.

Arms and their decisions (PREREG "Operating points"): the baselines and Llama Guard keep their native binary
decision (threshold 1.0 on a 0/1 score); `embed` scores each source with the fold model trained without it, at that
fold's dev threshold; `embed_all` is the shipped all-sources model at its own dev threshold. A missing, None or
non-finite score is unscored for that arm: excluded from its rates and counted, never guessed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
from collections import defaultdict
from collections.abc import Iterable, Mapping

from fusion_first.stats.metrics import wilson_interval
from fusion_first.validate.detector_data import read_jsonl
from fusion_first.validate.detector_eval import (
    _jsonable,
    auroc,
    bootstrap_auroc_ci,
    distinct_n,
    latency_summary,
    mcnemar_vs_reference,
    rates,
)
from fusion_first.validate.llama_guard import parse_verdict, tool_result_prompt
from fusion_first.validate.prereg import (
    DETECTOR_RECALL_FOLD,
    DETECTOR_SHIPPED_ARM,
    detector_decision,
)
from fusion_first.validate.seal import load_seal, seal_digest, verify_seal

CONFIRMATORY = "confirmatory"
# Repository-relative paths (the scripts resolve them from the repository root, never the working directory).
DATA = "datasets/detector/v1/confirmatory.jsonl"
SEAL = "evals/validation/v1/detector/confirmatory.seal.json"
DEV_LOSO = "evals/validation/v1/detector/dev_loso.json"
SUBSAMPLE = "evals/validation/v1/detector/lg3_subsample.json"
LG3_RAW = "evals/validation/v1/detector/lg3_raw.jsonl"
SCORES = "evals/validation/v1/detector/scores.jsonl"
EVIDENCE = "evals/validation/v1/detector/detector_v1.json"
PREREGISTRATION = "evals/validation/v1/PREREG_detector_v1.md"
KIND = "trained detector for injected tool results, confirmatory rows, scored once"

REFERENCE = "b1_phrase_list"
LOSO_ARM, SHIPPED_ARM = "embed", "embed_all"  # arms keys; the envelope's shipped tag is DETECTOR_SHIPPED_ARM
LG3_ARMS = {"configured": "llama_guard3_configured", "default": "llama_guard3_default"}
NATIVE_THRESHOLD, NATIVE_RULE = 1.0, "native_binary"
FPR_RULE = "fpr_0.01_on_training_dev_negatives"
# Outcome (2): the distinct confirmatory TOOL-RESULT negatives (InjecAgent minimal pairs, blind, BIPIA carrier
# controls); deepset negatives are prompts, reported separately (arms.embed_all.per_source.deepset).
SHIPPED_NEGATIVE_SOURCES = ("injecagent", "blind", "bipia")
SUBSAMPLE_RULE = ("equal allocation over source x label strata (a stratum smaller than its share gives the rest to "
                  "the others); within a stratum, ids ranked by sha256('<seed>:<id>'); interleaved across strata "
                  "so every prefix stays spread")


# ---------------------------------------------------------------- the sealed rows


def _against_seal(data_path, seal_path) -> tuple[list[dict], str, dict[str, list[str]]]:
    """(rows, seal digest, diff). The seal is loaded, and its own digest checked, before the rows are opened."""
    seal_path = pathlib.Path(seal_path)
    if not seal_path.is_file():
        raise FileNotFoundError(f"no seal at {seal_path}: the confirmatory rows are read only against their seal")
    seal = load_seal(seal_path)
    rows = read_jsonl(data_path)
    diff = {**verify_seal(rows, seal, split=CONFIRMATORY),
            "other_split": sorted(str(r.get("id")) for r in rows if r.get("split") != CONFIRMATORY)}
    return rows, seal_digest(seal), diff


def seal_diff(data_path: str | os.PathLike, seal_path: str | os.PathLike) -> dict[str, list[str]]:
    """Changed, missing and added confirmatory ids versus the seal, plus ids of rows outside the confirmatory split
    (all empty = intact)."""
    return _against_seal(data_path, seal_path)[2]


def sealed_rows(data_path: str | os.PathLike, seal_path: str | os.PathLike) -> tuple[list[dict], str]:
    """(the confirmatory rows, the seal's digest), only when the rows match the seal exactly; ValueError naming every
    changed, missing, added and out-of-split id otherwise. The rows returned are the rows verified."""
    rows, digest, diff = _against_seal(data_path, seal_path)
    if any(diff.values()):
        detail = "; ".join(f"{k}: {', '.join(v)}" for k, v in diff.items() if v)
        raise ValueError(f"{data_path} does not match the seal {seal_path} ({detail})")
    return rows, digest


# ---------------------------------------------------------------- the Llama Guard 3 subsample, prompt and replies


def _rank(seed: int, rid: str) -> tuple[str, str]:
    return hashlib.sha256(f"{seed}:{rid}".encode()).hexdigest(), rid


def stratified_subsample(rows: Iterable[dict], n: int, seed: int) -> list[str]:
    """`n` ids balanced over source x label strata (see SUBSAMPLE_RULE); deterministic for (rows, n, seed) and
    independent of row order."""
    strata: dict[tuple[str, int], list[str]] = defaultdict(list)
    for r in rows:
        strata[(r["source"], int(r["label"]))].append(r["id"])
    total = sum(len(v) for v in strata.values())
    if n < 1 or n > total:
        raise ValueError(f"asked for {n} rows but only {total} exist (n must be between 1 and {total})")
    keys = sorted(strata)
    alloc = dict.fromkeys(keys, 0)
    remaining = n
    while remaining:
        open_ = [k for k in keys if alloc[k] < len(strata[k])]
        share, extra = divmod(remaining, len(open_))
        for i, k in enumerate(open_):
            add = min(share + (i < extra), len(strata[k]) - alloc[k])
            alloc[k] += add
            remaining -= add
    picked = {k: sorted(strata[k], key=lambda rid: _rank(seed, rid))[:alloc[k]] for k in keys}
    return [picked[k][j] for j in range(max(alloc.values())) for k in keys if j < alloc[k]]


def lg3_prompt(row: Mapping, arm: str) -> str:
    """The registered Llama Guard 3 prompt for one row: the request and the tool result in the User turn, the Agent
    turn empty, the assessment of the last User message; `configured` adds S16 prompt injection."""
    return tool_result_prompt(row.get("request"), row.get("tool"), row["text"], arm)


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def lg3_score(output: str | None) -> float | None:
    """1.0 for an 'unsafe' first line, 0.0 for 'safe', None (unscored) for anything else."""
    return {"unsafe": 1.0, "safe": 0.0}.get(parse_verdict(output)["label"])


def load_subsample(path: str | os.PathLike, rows_by_id: Mapping[str, dict], digest: str) -> list[str]:
    """The subsample's ids, refused unless it was drawn from these sealed rows."""
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    ids = doc.get("ids")
    if doc.get("seal_digest") != digest:
        raise ValueError(f"{path} was drawn under seal {doc.get('seal_digest')!r}, not {digest!r}")
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        raise ValueError(f"{path} needs a non-empty list of distinct ids")
    unknown = [i for i in ids if i not in rows_by_id]
    if unknown:
        raise ValueError(f"{path} names ids outside the sealed rows: {', '.join(unknown[:5])}")
    return ids


def lg3_arm(records: Iterable[dict], arm: str, subsample: list[str], rows_by_id: Mapping[str, dict]) -> dict | None:
    """One Llama Guard arm from its recorded replies, or None without any. Its rows are the subsample prefix through
    the last recorded id (a `run --n N` covers the first N); a row in that prefix without a reply is unscored and
    counted as missing. Refuses a reply outside the subsample, a second reply for one row, a reply whose prompt hash
    is not the registered prompt's, or a stored verdict that its own output does not parse to."""
    position = {rid: k for k, rid in enumerate(subsample)}
    seen: dict[str, dict] = {}
    for rec in records:
        if rec.get("arm") != arm:
            continue
        rid = rec["id"]
        if rid not in position:
            raise ValueError(f"Llama Guard reply for {rid} ({arm}) is not in the subsample")
        if rid in seen:
            raise ValueError(f"two Llama Guard replies for {rid} ({arm})")
        if rec["prompt_sha256"] != prompt_sha256(lg3_prompt(rows_by_id[rid], arm)):
            raise ValueError(f"Llama Guard reply for {rid} ({arm}) was not made with the registered prompt")
        if rec["verdict"] != parse_verdict(rec["output"])["label"]:
            raise ValueError(f"Llama Guard reply for {rid} ({arm}): verdict {rec['verdict']!r} does not match "
                             "its output")
        seen[rid] = rec
    if not seen:
        return None
    ids = subsample[:max(position[rid] for rid in seen) + 1]
    scores = {rid: lg3_score(seen[rid]["output"]) if rid in seen else None for rid in ids}
    return {"ids": ids, "scores": scores,
            "latency_ms": [float(seen[rid]["seconds"]) * 1000.0 for rid in ids if rid in seen],
            "model_digest": sorted({str(rec.get("model_digest")) for rec in seen.values()}),
            "missing": sum(rid not in seen for rid in ids),
            "unparseable": sum(rid in seen and scores[rid] is None for rid in ids)}


# ---------------------------------------------------------------- arms and the envelope


def _finite(x: object) -> float | None:
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def threshold_json(t: float | None) -> float | str | None:
    """A threshold as strict JSON: +inf (flags nothing) as the string "inf", as dev_loso.json writes it."""
    return t if t is None or math.isfinite(t) else str(t)


def decide(score: float | None, threshold: float) -> bool | None:
    """The arm's decision on one row: flagged, not flagged, or None when the row is unscored."""
    s = _finite(score)
    return None if s is None else s >= threshold


def arm_block(rows: list[dict], scores: Mapping[str, float | None], thresholds: Mapping[str, float], *,
              label: str, threshold: float | None, threshold_rule: str, note: str,
              latency_ms: list[float] | None = None, **extra) -> tuple[dict, dict[str, bool | None]]:
    """(the arm's envelope block, its per-row decisions). `rows` are the arm's own rows in file order; `thresholds`
    gives each row's threshold (a LOSO arm's differs by source). Rates count the decisions (unscored rows excluded);
    AUROC ranks the raw scores of the scored rows."""
    flags = {r["id"]: decide(scores.get(r["id"]), thresholds[r["id"]]) for r in rows}
    binary = {rid: None if f is None else float(f) for rid, f in flags.items()}
    block = rates(rows, binary, 1.0)
    scored = [(r, s) for r in rows if (s := _finite(scores.get(r["id"]))) is not None]
    y, s = [bool(r["label"]) for r, _ in scored], [v for _, v in scored]
    per_source = defaultdict(list)
    for r, v in scored:
        per_source[r["source"]].append((bool(r["label"]), v))
    out = {"label": label, "threshold": threshold_json(threshold), "threshold_rule": threshold_rule, **block,
           "auroc": auroc(y, s), "auroc_ci": bootstrap_auroc_ci(y, s),
           "auroc_per_source": {k: auroc([t for t, _ in v], [x for _, x in v]) for k, v in sorted(per_source.items())},
           "latency": latency_summary(latency_ms) if latency_ms is not None else None,
           "n_rows": len(rows), "n_scored": len(scored), "note": note, **extra}
    return _jsonable(out), flags


def primary_recall(rows: list[dict], flags: Mapping[str, bool | None]) -> dict:
    """Outcome (1): recall on the confirmatory InjecAgent positives under the fold that never saw InjecAgent."""
    pos = [r for r in rows if r["source"] == "injecagent" and r["label"] == 1 and flags.get(r["id"]) is not None]
    tp = sum(bool(flags[r["id"]]) for r in pos)
    iv = wilson_interval(tp, len(pos))
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": len(pos), "tp": tp,
            "fold": DETECTOR_RECALL_FOLD, "arm": LOSO_ARM}


def primary_shipped_fpr(rows: list[dict], flags: Mapping[str, bool | None]) -> dict:
    """Outcome (2): the shipped model's false-positive rate on the distinct confirmatory tool-result negatives (a
    text is a false positive when any of its scored rows is flagged)."""
    texts: dict[str, bool] = {}
    for r in rows:
        if r["label"] == 0 and r["source"] in SHIPPED_NEGATIVE_SOURCES and flags.get(r["id"]) is not None:
            texts[r["text"]] = texts.get(r["text"], False) or bool(flags[r["id"]])
    fp = sum(texts.values())
    iv = wilson_interval(fp, len(texts))
    return {"point": iv.point, "low": iv.low, "high": iv.high, "n": len(texts), "fp": fp,
            "arm": DETECTOR_SHIPPED_ARM, "arms_key": SHIPPED_ARM, "sources": list(SHIPPED_NEGATIVE_SOURCES),
            "note": f"tag {DETECTOR_SHIPPED_ARM!r} (prereg.detector_decision) names the arm arms.{SHIPPED_ARM}; "
                    "distinct tool-result negatives only; deepset negatives (prompts, in-distribution) are reported "
                    f"separately in arms.{SHIPPED_ARM}.per_source.deepset"}


def build_envelope(rows: list[dict], arms: Mapping[str, dict], *, digest: str, absent: Mapping[str, str],
                   meta: Mapping) -> tuple[dict, list[dict]]:
    """(the evidence envelope, the scores.jsonl lines). `arms` maps an arm name to its inputs: `ids` (the rows it
    scores; all rows when absent), `scores`, `thresholds` (per row id) and `arm_block`'s keyword arguments. The
    registered arms `embed` and `embed_all` and the reference `b1_phrase_list` are required."""
    missing = [a for a in (LOSO_ARM, SHIPPED_ARM, REFERENCE) if a not in arms]
    if missing:
        raise ValueError(f"the registered arm(s) {', '.join(missing)} have no scores")
    blocks, flags, lines, arm_rows = {}, {}, [], {}
    for name, spec in arms.items():
        ids = spec.get("ids")
        chosen = set(ids) if ids is not None else None
        mine = [r for r in rows if chosen is None or r["id"] in chosen]
        kwargs = {k: v for k, v in spec.items() if k not in ("ids", "scores", "thresholds")}
        blocks[name], flags[name] = arm_block(mine, spec["scores"], spec["thresholds"], **kwargs)
        arm_rows[name] = mine
        lines += [{"id": r["id"], "arm": name, "score": _finite(spec["scores"].get(r["id"])),
                   "flagged": flags[name][r["id"]]} for r in mine]
    binary = {name: {rid: None if f is None else float(f) for rid, f in fl.items()} for name, fl in flags.items()}
    mcnemar = {name: mcnemar_vs_reference(arm_rows[name], {name: binary[name], REFERENCE: binary[REFERENCE]},
                                          {name: 1.0, REFERENCE: 1.0}, name, REFERENCE)
               for name in arms if name != REFERENCE}
    envelope = {"demonstration": False, "kind": KIND, "preregistration": PREREGISTRATION, **meta,
                "seal_digest": digest, "n_rows": len(rows), "arms": blocks,
                "primary": {"injecagent_recall": primary_recall(rows, flags[LOSO_ARM]),
                            "shipped_fpr": primary_shipped_fpr(rows, flags[SHIPPED_ARM])},
                "distinct_n": distinct_n(rows), "mcnemar_vs_phrase_list": _jsonable(mcnemar),
                "absent_arms": dict(absent)}
    envelope["decision"] = detector_decision(envelope)
    return envelope, lines
