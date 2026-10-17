"""Detector systems (dev-only): the baselines and the embedding + logistic arm of the tool-result injection
detector (PREREG_detector_v1.md).

- B0 `always_negative_score`: never flags.
- B1 `phrase_list_score`: the shipped phrase list, exactly `Guardrail.guard_input`'s test (`_INJECTION_PHRASES` over
  the raw text and its `normalized_views`). It scores the RAW tool result, not the frame: the guard sees only the
  untrusted text, so wrapping it in the frame would only add chances for the request to match.
- E `EmbeddingLogistic`: frozen `BAAI/bge-small-en-v1.5` sentence embeddings (normalized, 256-token inputs) and a
  class-balanced logistic regression. A frame longer than one window is cut by `chunk_frame` and scores the max over
  its chunks.

sentence-transformers, torch and scikit-learn are imported inside functions (the `detector` extra), so importing this
module costs nothing. The real embedder only reads the local Hugging Face cache: HF_HUB_OFFLINE and
TRANSFORMERS_OFFLINE are set before transformers is imported, and the model is loaded with local_files_only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import random
import sys
import time
from collections.abc import Callable, Iterable, Sequence

import numpy as np

from fusion_first.guardrail.guard import _INJECTION_PHRASES
from fusion_first.security.normalize import normalized_views
from fusion_first.validate.detector_data import render_frame

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
MAX_TOKENS = 256  # the model's input window, special tokens included (PREREG: 256-token windows)
STRIDE = 128
BATCH_SIZE = 32
SEED = 42
DEFAULT_CACHE = pathlib.Path(".fusion/detector-cache")
_DEFAULT = object()  # cache_dir not given

EmbedFn = Callable[[Sequence[str]], np.ndarray]


# ---------------------------------------------------------------- baselines


def phrase_list_score(text: str) -> float:
    """B1: 1.0 when the shipped phrase list matches the raw text or one of its normalized views, else 0.0."""
    views = [text, *normalized_views(text)]
    return 1.0 if any(p in v.lower() for v in views for p in _INJECTION_PHRASES) else 0.0


def always_negative_score(_: str) -> float:
    """B0: never flags."""
    return 0.0


def latency_ms(fn: Callable[[str], object], texts: Iterable[str]) -> list[float]:
    """Wall time of each single decision `fn(text)`, in milliseconds."""
    out = []
    for t in texts:
        start = time.perf_counter()
        fn(t)
        out.append((time.perf_counter() - start) * 1000.0)
    return out


def seed_everything(seed: int = SEED) -> None:
    """Python and numpy always; torch only when it is already loaded (the real embedder seeds it on load)."""
    random.seed(seed)
    np.random.seed(seed)
    if "torch" in sys.modules:
        sys.modules["torch"].manual_seed(seed)


# ---------------------------------------------------------------- chunking


def chunk_bounds(frame: str, tokenizer, max_tokens: int = MAX_TOKENS, stride: int = STRIDE) -> list[tuple[int, int]]:
    """Character bounds of the token windows over `frame`. A window holds `max_tokens` minus the tokenizer's special
    tokens, so each chunk fits the model's input; windows start every `stride` tokens until one reaches the end. With
    a fast tokenizer's `word_ids`, a window starts and ends on word boundaries (a cut subword re-tokenizes into more
    tokens than the window holds) unless that would leave a gap. A frame that fits (or no tokenizer) is one chunk,
    the whole frame."""
    if tokenizer is None:
        return [(0, len(frame))]
    special = getattr(tokenizer, "num_special_tokens_to_add", None)
    width = max_tokens - (special(pair=False) if callable(special) else 0)
    if width <= 0 or stride <= 0:
        raise ValueError("max_tokens must exceed the special tokens and stride must be positive")
    enc = tokenizer(frame, add_special_tokens=False, return_offsets_mapping=True, verbose=False)
    offsets = enc["offset_mapping"]
    n = len(offsets)
    if n <= width:
        return [(0, len(frame))]
    words = enc.word_ids() if callable(getattr(enc, "word_ids", None)) else None

    def word_start(i: int) -> int:
        """The first token of token i's word (subword tokens re-tokenize differently when cut from their word)."""
        while words is not None and 0 < i < n and words[i] is not None and words[i - 1] == words[i]:
            i -= 1
        return i

    bounds = []
    for start in range(0, n, stride):
        s = word_start(start)
        s = s if start - s <= width - stride else start  # a window must still reach the next window's start
        end = min(s + width, n)
        e = word_start(end) if end < n else n
        e = e if e >= start + stride else end  # one word longer than the overlap is cut where it falls
        bounds.append((0 if s == 0 else offsets[s][0], len(frame) if e == n else offsets[e - 1][1]))
        if e == n:
            break
    return bounds


def chunk_frame(frame: str, tokenizer, max_tokens: int = MAX_TOKENS, stride: int = STRIDE) -> list[str]:
    """The frame's token windows as text (see `chunk_bounds`). A text's score is the max over its chunks."""
    return [frame[a:b] for a, b in chunk_bounds(frame, tokenizer, max_tokens, stride)]


def _reliable_span(row: dict) -> list[int] | None:
    prov = row.get("provenance") or {}
    span = prov.get("span")
    return None if not span or prov.get("span_unreliable") else span


def training_examples(rows: Iterable[dict], tokenizer, max_tokens: int = MAX_TOKENS,
                      stride: int = STRIDE) -> tuple[list[str], list[int]]:
    """Model inputs and labels for training. A frame that fits is one example with its row's label. A long frame
    is chunked: a negative's chunks are all 0; a positive's chunks are 1 where they overlap its injected span and 0
    elsewhere. A long positive without a reliable span (none, or `provenance.span_unreliable`) is one text-level
    example: the whole frame, label 1."""
    texts, labels = [], []
    for row in rows:
        frame = render_frame(row)
        bounds = chunk_bounds(frame, tokenizer, max_tokens, stride)
        label = int(row["label"])
        span = _reliable_span(row) if label else None
        if len(bounds) == 1 or (label and span is None):
            texts.append(frame)
            labels.append(label)
            continue
        offset = len(frame) - len(row["text"])  # the text closes the frame
        lo, hi = (span[0] + offset, span[1] + offset) if span else (0, 0)
        for a, b in bounds:
            texts.append(frame[a:b])
            labels.append(int(bool(span) and a < hi and lo < b))
    return texts, labels


# ---------------------------------------------------------------- embeddings


def bge_embedder(model_name: str = EMBED_MODEL, *, max_seq_length: int = MAX_TOKENS, batch_size: int = BATCH_SIZE,
                 seed: int = SEED) -> tuple[EmbedFn, object]:
    """(embed_fn, tokenizer) for the frozen local bge-small on CPU: normalized float32 vectors. Offline only."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(seed)
    model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
    model.max_seq_length = max_seq_length
    model.eval()

    def embed(texts: Sequence[str]) -> np.ndarray:
        return model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True,
                            show_progress_bar=False)

    return embed, model.tokenizer


class CachedEmbedder:
    """Memoizes an embed_fn in memory and, given a directory, on disk as `<sha256(input)>.npy`."""

    def __init__(self, embed_fn: EmbedFn, cache_dir: str | os.PathLike | None = None):
        self.embed_fn = embed_fn
        self.cache_dir = pathlib.Path(cache_dir) if cache_dir is not None else None
        self._memo: dict[str, np.ndarray] = {}

    def _load(self, key: str) -> np.ndarray | None:
        if key in self._memo:
            return self._memo[key]
        if self.cache_dir is not None and (path := self.cache_dir / f"{key}.npy").is_file():
            self._memo[key] = np.load(path)
            return self._memo[key]
        return None

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        keys = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
        todo = {k: t for k, t in zip(keys, texts, strict=True) if self._load(k) is None}
        if todo:
            vecs = np.asarray(self.embed_fn(list(todo.values())))
            if self.cache_dir is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            for k, v in zip(todo, vecs, strict=True):
                self._memo[k] = v
                if self.cache_dir is not None:
                    np.save(self.cache_dir / f"{k}.npy", v)
        return np.stack([self._memo[k] for k in keys]) if keys else np.zeros((0, 0), dtype=np.float32)


def _encode_float(x: float | None) -> float | str | None:
    return x if x is None or math.isfinite(x) else str(x)


class EmbeddingLogistic:
    """Frozen sentence embeddings plus `LogisticRegression(class_weight="balanced", max_iter=1000)`.

    `fit` takes model inputs as given (see `training_examples`); `scores` takes frames, chunks each and returns the
    max chunk probability. Probabilities are the logistic of the fitted linear score, computed here from the saved
    coefficients so a loaded model scores bit-for-bit like the fitted one. Without `embed_fn` the local bge-small is
    loaded on first use and embeddings are cached under `.fusion/detector-cache/`; with an injected `embed_fn` only
    an explicit `cache_dir` is used. `threshold` is the operating threshold chosen by the caller (saved with the
    model)."""

    def __init__(self, embed_fn: EmbedFn | None = None, tokenizer=None, *, cache_dir=_DEFAULT,
                 max_tokens: int = MAX_TOKENS, stride: int = STRIDE, seed: int = SEED):
        self._embed_fn, self._tokenizer, self._cache_dir = embed_fn, tokenizer, cache_dir
        self._embedder: CachedEmbedder | None = embed_fn if isinstance(embed_fn, CachedEmbedder) else None
        self.max_tokens, self.stride, self.seed = max_tokens, stride, seed
        self.coef: np.ndarray | None = None
        self.intercept = 0.0
        self.threshold: float | None = None
        self.n_train = 0

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        if self._embedder is None:
            fn, cache = self._embed_fn, self._cache_dir
            if fn is None:
                fn, tokenizer = bge_embedder(seed=self.seed)
                self._tokenizer = self._tokenizer or tokenizer
                cache = DEFAULT_CACHE if cache is _DEFAULT else cache
            self._embedder = CachedEmbedder(fn, None if cache is _DEFAULT else cache)
        return self._embedder(texts)

    @property
    def tokenizer(self):
        if self._tokenizer is None and self._embed_fn is None and self._embedder is None:
            self._embed([])  # loads bge-small and its tokenizer
        return self._tokenizer

    def fit(self, frames: Sequence[str], labels: Sequence[int]) -> EmbeddingLogistic:
        from sklearn.linear_model import LogisticRegression

        clf = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=self.seed)
        clf.fit(self._embed(frames), np.asarray(labels, dtype=int))
        self.coef = np.asarray(clf.coef_[0], dtype=np.float64)
        self.intercept = float(clf.intercept_[0])
        self.n_train = len(frames)
        return self

    def chunk_scores(self, inputs: Sequence[str]) -> list[float]:
        """Probability for each model input as given (no chunking)."""
        if self.coef is None:
            raise ValueError("EmbeddingLogistic is not fitted")
        if not inputs:
            return []
        z = self._embed(inputs).astype(np.float64) @ self.coef + self.intercept
        return (1.0 / (1.0 + np.exp(-z))).tolist()

    def scores(self, frames: Sequence[str]) -> list[float]:
        """Each frame's score: the max probability over its chunks."""
        chunks = [chunk_frame(f, self.tokenizer, self.max_tokens, self.stride) for f in frames]
        flat = self.chunk_scores([c for cs in chunks for c in cs])
        out, i = [], 0
        for cs in chunks:
            out.append(max(flat[i:i + len(cs)]))
            i += len(cs)
        return out

    def save(self, directory: str | os.PathLike) -> None:
        if self.coef is None:
            raise ValueError("EmbeddingLogistic is not fitted")
        d = pathlib.Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / "coef.npy", self.coef)
        meta = {"embedder": EMBED_MODEL, "normalize_embeddings": True, "max_seq_length": MAX_TOKENS,
                "max_tokens": self.max_tokens, "stride": self.stride, "intercept": self.intercept,
                "threshold": _encode_float(self.threshold), "n_train": self.n_train, "seed": self.seed,
                "classifier": "sklearn LogisticRegression(class_weight='balanced', max_iter=1000)"}
        (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")

    @classmethod
    def load(cls, directory: str | os.PathLike, embed_fn: EmbedFn | None = None, tokenizer=None, *,
             cache_dir=_DEFAULT) -> EmbeddingLogistic:
        d = pathlib.Path(directory)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        model = cls(embed_fn, tokenizer, cache_dir=cache_dir, max_tokens=meta["max_tokens"], stride=meta["stride"],
                    seed=meta["seed"])
        model.coef = np.load(d / "coef.npy")
        model.intercept = float(meta["intercept"])
        model.threshold = None if meta["threshold"] is None else float(meta["threshold"])
        model.n_train = meta["n_train"]
        return model
