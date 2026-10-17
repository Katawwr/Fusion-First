"""Arm F (dev-only, optional): bge-small fine-tuned as a 2-label sequence classifier for the tool-result injection
detector (PREREG_detector_v1.md: "F optional fine-tune of bge-small (two named folds: hold out InjecAgent; hold out
AgentDojo)"; dropping F is not a protocol change).

`FineTunedClassifier` puts `AutoModelForSequenceClassification` (num_labels 2) on `BAAI/bge-small-en-v1.5`, the only
backbone allowed, and trains it with a plain torch loop: AdamW, a linear schedule with 6% warmup, cross-entropy, a
seeded shuffle; python, numpy and torch are seeded before the backbone is loaded, so the new head is seeded too.
`fit` takes model inputs as given (the LOSO driver builds them with `detector_systems.training_examples`, the same
chunk labels as arm E). `scores` takes frames, cuts each into the registered windows with `chunk_frame` and returns
the max over its chunks of the softmax probability of class 1 (computed in float64 from the logits, so confident
scores do not tie at 1.0). Each input is scored on its own, without padding, so a score never depends on the other
texts in the call and a loaded model reproduces the fitted one bit for bit.

The window follows `max_len` (`window`): `max_len` tokens with stride `max_len // 2`. The default, 256, is the
registered rule (256-token windows, stride 128); an override is a departure recorded in meta.json and in the
readout. Torch and transformers are imported inside functions (the `detector` extra), so importing this module costs
nothing; HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE are set before transformers is imported and every load passes
local_files_only, so nothing is downloaded. Nothing here imports modal.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import pathlib
import random
import subprocess
from collections.abc import Iterator, Sequence

import numpy as np

from fusion_first.validate import detector_systems as ds

BACKBONE = ds.EMBED_MODEL  # the only backbone allowed for arm F
INJECTED = ds.INJECTED  # the backbone name recorded for a caller-supplied model
NUM_LABELS = 2
EPOCHS = 3
BATCH_SIZE = 16
LR = 3e-5
WEIGHT_DECAY = 0.01  # torch's AdamW default, recorded
WARMUP = 0.06  # share of the optimizer steps spent warming up, then linear decay to 0
MAX_LEN = ds.MAX_TOKENS  # model input length in tokens, special tokens included; the window follows it
SEED = ds.SEED
THREADS = 4
SCORE = "softmax probability of class 1 (float64 from the logits), max over chunks"


def window(max_len: int) -> tuple[int, int]:
    """(window tokens, stride) for a model input of `max_len` tokens: the registered 256 / 128 at the default."""
    return max_len, max_len // 2


def _offline() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def _torch():
    _offline()
    import torch

    return torch


@contextlib.contextmanager
def _threads(torch, n: int) -> Iterator[None]:
    """Run with `n` torch threads and give the caller's count back."""
    before = torch.get_num_threads()
    torch.set_num_threads(n)
    try:
        yield
    finally:
        torch.set_num_threads(before)


def _seed(torch, seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def git_sha() -> str:
    """HEAD of the checkout this module lives in ("" outside a git checkout)."""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ds.REPO_ROOT, capture_output=True, text=True,
                           check=False)
    except OSError:
        return ""
    return r.stdout.strip()


def _encode_float(x: float | None) -> float | str | None:
    """JSON-safe: an infinite threshold (nothing flags) is written as the string "inf"."""
    return x if x is None or math.isfinite(x) else str(x)


def _float(x: object) -> float | None:
    return None if x is None else float(x)


class FineTunedClassifier:
    """bge-small with a 2-label classification head, fine-tuned end to end (arm F).

    `backbone` is BACKBONE (the default; loaded from the local Hugging Face cache, the model when `fit` starts, its
    tokenizer on first use) or a preloaded `...ForSequenceClassification` model with 2 labels, which needs its
    `tokenizer` and is trained in place; meta.json names it `backbone_name` (default "injected"). `threshold` is the
    operating threshold chosen by the caller (saved with the model)."""

    def __init__(self, backbone: object = BACKBONE, tokenizer=None, *, backbone_name: str | None = None,
                 threads: int = THREADS):
        self._named = isinstance(backbone, str)
        if self._named:
            if backbone != BACKBONE:
                raise ValueError(f"arm F fine-tunes {BACKBONE} (bge-small) only, not {backbone!r}")
            self._model, self.backbone_name = None, BACKBONE
        else:
            if tokenizer is None:
                raise ValueError("a preloaded backbone needs its tokenizer (chunking and inputs use it)")
            labels = getattr(getattr(backbone, "config", None), "num_labels", NUM_LABELS)
            if labels != NUM_LABELS:
                raise ValueError(f"a preloaded backbone needs a {NUM_LABELS}-label head, not {labels}")
            self._model, self.backbone_name = backbone, backbone_name or INJECTED
        self._tokenizer = tokenizer
        self.max_len, self.stride = window(MAX_LEN)
        self.threads = threads
        self.threshold: float | None = None
        self.n_train = 0
        self.fitted = False
        self.training: dict = {}

    # ------------------------------------------------------------ loading

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            _offline()
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.backbone_name, local_files_only=True)
        return self._tokenizer

    def _backbone_for_training(self):
        """The model to train: a fresh bge-small with a new (seeded) head, or the preloaded model as it stands."""
        if self._named:
            _offline()
            from transformers import AutoModelForSequenceClassification

            return AutoModelForSequenceClassification.from_pretrained(BACKBONE, num_labels=NUM_LABELS,
                                                                      local_files_only=True)
        return self._model

    # ------------------------------------------------------------ training

    def fit(self, texts: Sequence[str], labels: Sequence[int], *, epochs: int = EPOCHS,
            batch_size: int = BATCH_SIZE, lr: float = LR, max_len: int = MAX_LEN, seed: int = SEED,
            threads: int = THREADS) -> FineTunedClassifier:
        """Fine-tune on `texts` (model inputs, one window each) with labels 0/1. A named backbone starts fresh on
        every call; a preloaded one continues from its current weights."""
        texts, y = list(texts), [int(v) for v in labels]
        if not texts or len(texts) != len(y):
            raise ValueError("fit needs as many labels as texts, and at least one text")
        if set(y) - {0, 1}:
            raise ValueError("labels are 0 or 1")
        if epochs < 1 or batch_size < 1 or lr <= 0 or threads < 1:
            raise ValueError("epochs, batch_size and threads must be at least 1 and lr positive")
        if max_len < 4:
            raise ValueError("max_len must leave room for the special tokens and a window of stride max_len // 2")
        torch = _torch()
        from transformers import get_linear_schedule_with_warmup

        tok = self.tokenizer
        with _threads(torch, threads):
            _seed(torch, seed)
            model = self._backbone_for_training()
            limit = getattr(getattr(model, "config", None), "max_position_embeddings", None)
            if limit is not None and max_len > limit:
                raise ValueError(f"max_len {max_len} exceeds the backbone's {limit} positions")
            n = len(texts)
            steps = epochs * math.ceil(n / batch_size)
            warmup = math.ceil(WARMUP * steps)
            opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
            schedule = get_linear_schedule_with_warmup(opt, warmup, steps)
            target = torch.tensor(y, dtype=torch.long)
            order_rng = torch.Generator().manual_seed(seed)
            model.train()
            for _ in range(epochs):
                order = torch.randperm(n, generator=order_rng).tolist()
                for i in range(0, n, batch_size):
                    idx = order[i:i + batch_size]
                    batch = tok([texts[j] for j in idx], truncation=True, max_length=max_len, padding=True,
                                return_tensors="pt")
                    loss = torch.nn.functional.cross_entropy(model(**batch).logits, target[idx])
                    loss.backward()
                    opt.step()
                    schedule.step()
                    opt.zero_grad(set_to_none=True)
            model.eval()
        self._model = model
        self.max_len, self.stride = window(max_len)
        self.threads, self.n_train, self.fitted = threads, n, True
        self.training = {"epochs": epochs, "batch_size": batch_size, "lr": lr, "seed": seed,
                         "warmup_ratio": WARMUP, "warmup_steps": warmup, "steps": steps,
                         "weight_decay": WEIGHT_DECAY}
        return self

    # ------------------------------------------------------------ scoring

    def chunk_scores(self, inputs: Sequence[str]) -> list[float]:
        """P(class 1) for each model input as given (no chunking), each scored on its own."""
        if not self.fitted:
            raise ValueError("FineTunedClassifier is not fitted")
        if not inputs:
            return []
        torch = _torch()
        tok, out = self.tokenizer, []
        with _threads(torch, self.threads), torch.inference_mode():
            for text in inputs:
                enc = tok(text, truncation=True, max_length=self.max_len, return_tensors="pt")
                logits = self._model(**enc).logits[0].to(torch.float64)
                out.append(float(torch.softmax(logits, dim=-1)[1]))
        return out

    def scores(self, frames: Sequence[str]) -> list[float]:
        """Each frame's score: the max over its `chunk_frame` windows."""
        if not self.fitted:
            raise ValueError("FineTunedClassifier is not fitted")
        tok = self.tokenizer
        chunks = [ds.chunk_frame(f, tok, self.max_len, self.stride) for f in frames]
        flat = self.chunk_scores([c for cs in chunks for c in cs])
        out, i = [], 0
        for cs in chunks:
            out.append(max(flat[i:i + len(cs)]))
            i += len(cs)
        return out

    # ------------------------------------------------------------ persistence

    def meta(self) -> dict:
        return {"arm": "F", "backbone": self.backbone_name, "num_labels": NUM_LABELS, "max_len": self.max_len,
                "max_tokens": self.max_len, "stride": self.stride, **self.training, "threads": self.threads,
                "n_train": self.n_train, "threshold": _encode_float(self.threshold), "git_sha": git_sha(),
                "optimizer": "torch AdamW", "schedule": "linear with warmup", "loss": "cross-entropy",
                "score": SCORE}

    def save(self, directory: str | os.PathLike) -> None:
        """Weights and tokenizer (`save_pretrained`) plus meta.json."""
        if not self.fitted:
            raise ValueError("FineTunedClassifier is not fitted")
        d = pathlib.Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self._model.save_pretrained(d)
        self.tokenizer.save_pretrained(d)
        (d / "meta.json").write_text(json.dumps(self.meta(), indent=2) + "\n", encoding="utf-8", newline="\n")

    @classmethod
    def load(cls, directory: str | os.PathLike) -> FineTunedClassifier:
        d = pathlib.Path(directory)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        _offline()
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model = AutoModelForSequenceClassification.from_pretrained(d, local_files_only=True)
        model.eval()
        tokenizer = AutoTokenizer.from_pretrained(d, local_files_only=True)
        clf = cls(model, tokenizer, backbone_name=meta["backbone"], threads=meta["threads"])
        clf.max_len, clf.stride = meta["max_len"], meta["stride"]
        clf.threshold = _float(meta["threshold"])
        clf.n_train, clf.fitted = meta["n_train"], True
        clf.training = {k: meta[k] for k in ("epochs", "batch_size", "lr", "seed", "warmup_ratio", "warmup_steps",
                                             "steps", "weight_decay") if k in meta}
        return clf
