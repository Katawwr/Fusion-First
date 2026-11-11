"""Off-the-shelf prompt-injection classifiers as baselines (dev-only; `evals/validation/v1/PREREG_guard_vs_detectors.md`).

Two sequence classifiers, each pinned to a Hub revision and to the sha256 of its weights:

- `prompt_guard_1`: `meta-llama/Prompt-Guard-86M`, labels BENIGN / INJECTION / JAILBREAK. Score = P(INJECTION) +
  P(JAILBREAK): the model card's score for third-party content such as tool outputs.
- `protectai`: `protectai/deberta-v3-base-prompt-injection-v2`, labels SAFE / INJECTION. Score = P(INJECTION).

A text is flagged when its score is at or above THRESHOLD in any window (MAX_TOKENS tokens, special tokens included,
every STRIDE tokens). Nothing here is fitted or tuned.

torch and transformers are imported inside `load` (the test suite needs neither), and the weights are read from the
local Hugging Face cache only: HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE are set and every call passes
`local_files_only`. A raw record keeps each window's logits, so `rescore` and `verified_flags` re-derive every score
and flag offline, with no model, and refuse a record whose text, model or arithmetic is not the registered one.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

MAX_TOKENS = 512  # both models' input window
STRIDE = 256
THRESHOLD = 0.5
INPUTS = ("tool_result", "user_turn")  # the registered input, and the sensitivity input (secondary)
WEIGHTS_FILE = "model.safetensors"


@dataclass(frozen=True)
class Classifier:
    name: str
    repo: str
    revision: str  # the Hub commit the weights were downloaded at
    weights_sha256: str
    labels: tuple[str, ...]  # id2label in index order, upper-cased; checked when the model is loaded
    positive: tuple[int, ...]  # the label indices whose probabilities add up to the score
    license: str


CLASSIFIERS: dict[str, Classifier] = {
    "prompt_guard_1": Classifier(
        name="prompt_guard_1", repo="meta-llama/Prompt-Guard-86M",
        revision="1209add6ca7d9c1d815171b8e5571587fe3e7b03",
        weights_sha256="1771712866662626517f2d85057de2d7078389a4c1f0bc93e461bdc4fdae4bd5",
        labels=("BENIGN", "INJECTION", "JAILBREAK"), positive=(1, 2), license="Llama 3.1 Community License"),
    "protectai": Classifier(
        name="protectai", repo="protectai/deberta-v3-base-prompt-injection-v2",
        revision="90c9989b1a342275dd0d1a95aad283c04e075671",
        weights_sha256="6521cb8d0ac08148c81464899c424e6148fcc62befa371089fa4061d8b6e0424",
        labels=("SAFE", "INJECTION"), positive=(1,), license="Apache-2.0"),
}

Forward = Callable[[str], Sequence[float]]  # one window's text -> its logits, in label order


class Loaded(NamedTuple):
    spec: Classifier
    tokenizer: object
    forward: Forward
    versions: dict


# ---------------------------------------------------------------- arithmetic (no model)


def input_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def softmax(logits: Sequence[float]) -> list[float]:
    top = max(logits)
    exps = [math.exp(x - top) for x in logits]
    total = sum(exps)
    return [e / total for e in exps]


def window_score(logits: Sequence[float], positive: Sequence[int]) -> float:
    probs = softmax(logits)
    return sum(probs[i] for i in positive)


def rescore(windows: Sequence[Sequence[float]], spec: Classifier) -> tuple[float, bool]:
    """(score, flagged) from the windows' logits: the highest window score, flagged at or above THRESHOLD."""
    if not windows or any(len(w) != len(spec.labels) for w in windows):
        raise ValueError(f"{spec.name}: expected {len(spec.labels)} logits per window, got {windows!r}"[:200])
    score = max(window_score(w, spec.positive) for w in windows)
    return score, score >= THRESHOLD


# ---------------------------------------------------------------- running a model


def classify(loaded: Loaded, text: str) -> dict:
    """One text through one classifier: every window's logits, the score and the flag."""
    from fusion_first.validate.detector_systems import chunk_bounds  # numpy stays lazy

    started = time.perf_counter()
    bounds = chunk_bounds(text, loaded.tokenizer, MAX_TOKENS, STRIDE)
    windows = [[float(x) for x in loaded.forward(text[a:b])] for a, b in bounds]
    score, flagged = rescore(windows, loaded.spec)
    return {"windows": windows, "score": score, "flagged": flagged,
            "seconds": round(time.perf_counter() - started, 4)}


def record(loaded: Loaded, rid: str, kind: str, text: str) -> dict:
    """The raw record of one decision: what was read (by hash), which model read it, and the logits it gave."""
    if kind not in INPUTS:
        raise ValueError(f"unknown input {kind!r}: one of {', '.join(INPUTS)}")
    spec = loaded.spec
    return {"classifier": spec.name, "repo": spec.repo, "revision": spec.revision,
            "weights_sha256": spec.weights_sha256, "id": rid, "input": kind, "input_sha256": input_sha256(text),
            **classify(loaded, text), "versions": dict(loaded.versions)}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(spec: Classifier) -> Loaded:
    """The pinned model from the local Hugging Face cache, on CPU. Refuses an unpinned classifier, weights whose
    sha256 is not the pinned one, and a label map other than the registered one."""
    if not spec.revision or not spec.weights_sha256:
        raise RuntimeError(f"{spec.name} is not pinned to a revision and a weights hash yet")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    import transformers
    from huggingface_hub import hf_hub_download
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    weights = hf_hub_download(spec.repo, WEIGHTS_FILE, revision=spec.revision, local_files_only=True)
    found = _sha256_file(weights)
    if found != spec.weights_sha256:
        raise RuntimeError(f"{spec.name}: {WEIGHTS_FILE} hashes to {found}, not the pinned {spec.weights_sha256}")
    tokenizer = AutoTokenizer.from_pretrained(spec.repo, revision=spec.revision, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(spec.repo, revision=spec.revision,
                                                               local_files_only=True)
    model.eval()
    labels = tuple(str(model.config.id2label[i]).upper() for i in range(model.config.num_labels))
    if labels != spec.labels:
        raise RuntimeError(f"{spec.name}: the model's labels are {labels}, not the registered {spec.labels}")

    def forward(text: str) -> list[float]:
        enc = tokenizer(text, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
        with torch.no_grad():
            return model(**enc).logits[0].tolist()

    return Loaded(spec, tokenizer, forward, {"torch": torch.__version__, "transformers": transformers.__version__})


# ---------------------------------------------------------------- reading the records back


def verified_flags(records: Iterable[dict], spec: Classifier, texts: Mapping[tuple[str, str], str]) -> dict:
    """{(id, input): flagged} for every text in `texts` = {(id, input): text}, re-derived from the records' logits.
    Refuses a record from another model or revision, one whose input hash is not the text's, one whose stored score
    or flag its logits do not reproduce, a duplicate, and a text with no record."""
    out: dict[tuple[str, str], bool] = {}
    for r in records:
        if r.get("classifier") != spec.name:
            continue
        key = (r["id"], r["input"])
        if key not in texts:
            continue
        where = f"{spec.name} {key[0]} ({key[1]})"
        if key in out:
            raise ValueError(f"{where}: recorded twice")
        if (r.get("repo"), r.get("revision"), r.get("weights_sha256")) != (
                spec.repo, spec.revision, spec.weights_sha256):
            raise ValueError(f"{where}: recorded by another model or revision")
        if r.get("input_sha256") != input_sha256(texts[key]):
            raise ValueError(f"{where}: the recorded input is not the registered text")
        score, flagged = rescore(r["windows"], spec)
        if flagged != r.get("flagged") or not math.isclose(score, r.get("score", -1.0), abs_tol=1e-9):
            raise ValueError(f"{where}: the stored score or flag does not follow from the logits")
        out[key] = flagged
    missing = sorted(k for k in texts if k not in out)
    if missing:
        raise ValueError(f"{spec.name}: no record for {len(missing)} text(s), first {missing[0]}")
    return out
