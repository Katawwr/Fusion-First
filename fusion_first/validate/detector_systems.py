"""Detector systems (dev-only): the baselines and the embedding + logistic arm of the tool-result injection
detector (PREREG_detector_v1.md).

- B0 `always_negative_score`: never flags.
- B1 `phrase_list_score`: the shipped phrase list, exactly `Guardrail.guard_input`'s test (`_INJECTION_PHRASES` over
  the raw text and its `normalized_views`). It scores the RAW tool result, not the frame: the guard sees only the
  untrusted text, so wrapping it in the frame would only add chances for the request to match.
  The baselines keep their native binary decision (PREREG "Operating points"): a score of 1.0 flags; the 1%
  false-positive-rate threshold rule applies only to the learned arms.
- E `EmbeddingLogistic`: frozen `BAAI/bge-small-en-v1.5` sentence embeddings (normalized, 256-token inputs) and a
  class-balanced logistic regression. A frame longer than one window is cut by `chunk_frame` (256-token windows,
  stride 128) and scores the max over its chunks. Chunking needs the embedder's tokenizer: an injected `embed_fn`
  must come with its `tokenizer`, or the caller opts out explicitly with `allow_unchunked=True`.

Training labels follow PREREG "Long texts" (`training_examples`): a frame that fits one window is one example with its
row's label; a long negative's chunks are all 0; a long positive with a reliable span has a chunk labelled 1 when the
chunk contains the whole injected span, or, when the span is wider than one window, when the chunk lies inside the
span or overlaps it by at least half the chunk's tokens; every other chunk is 0. A long positive whose span is
missing or flagged unreliable by the builder (`provenance.span_unreliable`) is excluded from training and reported;
every row is still scored text-level, max over chunks.

sentence-transformers, torch and scikit-learn are imported inside functions (the `detector` extra), so importing this
module costs nothing. The real embedder only reads the local Hugging Face cache: HF_HUB_OFFLINE and
TRANSFORMERS_OFFLINE are set before transformers is imported, and the model is loaded with local_files_only. Its
embeddings are cached under `<repo>/.fusion/detector-cache/<model>-seq<max_seq_length>/<sha256(input)>.npy`; the
repository root is the directory holding pyproject.toml above this module, never the working directory.
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
from typing import NamedTuple

import numpy as np

from fusion_first.guardrail.guard import _INJECTION_PHRASES
from fusion_first.security.normalize import normalized_views
from fusion_first.validate.detector_data import render_frame

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
INJECTED = "injected"  # the embedder name recorded for a caller-supplied embed_fn
MAX_TOKENS = 256  # the model's input window, special tokens included (PREREG: 256-token windows)
STRIDE = 128
BATCH_SIZE = 32
SEED = 42
_DEFAULT = object()  # cache_dir not given


def _repo_root() -> pathlib.Path:
    """The checkout this module lives in: the nearest parent directory holding pyproject.toml."""
    here = pathlib.Path(__file__).resolve()
    return next((d for d in here.parents if (d / "pyproject.toml").is_file()), here.parents[2])


REPO_ROOT = _repo_root()
CACHE_ROOT = REPO_ROOT / ".fusion" / "detector-cache"
DEFAULT_MODELS = REPO_ROOT / ".fusion" / "detector-models"


def embedding_cache_dir(model_name: str = EMBED_MODEL, max_seq_length: int = MAX_TOKENS,
                        root: str | os.PathLike | None = None) -> pathlib.Path:
    """`<root>/<model name, '/' as '--'>-seq<max_seq_length>`: one directory per embedder and input length, so a
    cached vector is never reused for another model or truncation. `root` defaults to CACHE_ROOT."""
    base = pathlib.Path(root) if root is not None else CACHE_ROOT
    return base / f"{model_name.replace('/', '--')}-seq{max_seq_length}"


DEFAULT_CACHE = embedding_cache_dir()

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


def _windows(frame: str, tokenizer, max_tokens: int, stride: int) -> tuple[list, list[tuple[int, int]], int]:
    """(token character offsets, token windows [start, end), window width in tokens). A window holds `max_tokens`
    minus the tokenizer's special tokens; windows start every `stride` tokens until one reaches the end."""
    if tokenizer is None:
        raise ValueError("chunking needs the embedder's tokenizer (PREREG: 256-token windows, stride 128)")
    special = getattr(tokenizer, "num_special_tokens_to_add", None)
    width = max_tokens - (special(pair=False) if callable(special) else 0)
    if width <= 0 or stride <= 0 or stride > width:
        raise ValueError(f"need 0 < stride <= window width: max_tokens={max_tokens} leaves {width} tokens after "
                         f"special tokens and stride={stride} (a stride wider than the window skips tokens)")
    enc = tokenizer(frame, add_special_tokens=False, return_offsets_mapping=True, verbose=False)
    offsets = enc["offset_mapping"]
    n = len(offsets)
    if n <= width:
        return offsets, [(0, n)], width
    words = enc.word_ids() if callable(getattr(enc, "word_ids", None)) else None

    def word_start(i: int) -> int:
        """The first token of token i's word (subword tokens re-tokenize differently when cut from their word)."""
        while words is not None and 0 < i < n and words[i] is not None and words[i - 1] == words[i]:
            i -= 1
        return i

    windows = []
    for start in range(0, n, stride):
        s = word_start(start)
        s = s if start - s <= width - stride else start  # a window must still reach the next window's start
        end = min(s + width, n)
        e = word_start(end) if end < n else n
        e = e if e >= start + stride else end  # one word longer than the overlap is cut where it falls
        windows.append((s, e))
        if e == n:
            break
    return offsets, windows, width


def _char_bounds(frame: str, offsets, windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    n = len(offsets)
    return [(0 if s == 0 else offsets[s][0], len(frame) if e == n else offsets[e - 1][1]) for s, e in windows]


def chunk_bounds(frame: str, tokenizer, max_tokens: int = MAX_TOKENS, stride: int = STRIDE) -> list[tuple[int, int]]:
    """Character bounds of the token windows over `frame`. A window holds `max_tokens` minus the tokenizer's special
    tokens, so each chunk fits the model's input; windows start every `stride` tokens until one reaches the end. With
    a fast tokenizer's `word_ids`, a window starts and ends on word boundaries (a cut subword re-tokenizes into more
    tokens than the window holds) unless that would leave a gap. A frame that fits is one chunk, the whole frame.
    Raises ValueError without a tokenizer, or when the stride is not positive or wider than the window."""
    offsets, windows, _ = _windows(frame, tokenizer, max_tokens, stride)
    return _char_bounds(frame, offsets, windows)


def chunk_frame(frame: str, tokenizer, max_tokens: int = MAX_TOKENS, stride: int = STRIDE) -> list[str]:
    """The frame's token windows as text (see `chunk_bounds`). A text's score is the max over its chunks."""
    return [frame[a:b] for a, b in chunk_bounds(frame, tokenizer, max_tokens, stride)]


def _reliable_span(row: dict) -> list[int] | None:
    prov = row.get("provenance") or {}
    span = prov.get("span")
    return None if not span or prov.get("span_unreliable") else span


def _span_tokens(offsets, lo: int, hi: int) -> tuple[int, int] | None:
    """The token range [first, last + 1) of the tokens that overlap the character span [lo, hi), if any."""
    hit = [i for i, (a, b) in enumerate(offsets) if a < hi and lo < b]
    return (hit[0], hit[-1] + 1) if hit else None


def _chunk_labels(windows: list[tuple[int, int]], span: tuple[int, int], width: int) -> list[int]:
    """PREREG "Long texts", on token ranges: a chunk is positive when it contains the whole span; when the span is
    wider than one window, a chunk is positive when it lies inside the span or overlaps it by at least half of the
    chunk's own tokens. Every other chunk is negative."""
    ts, te = span
    if te - ts <= width:
        return [int(s <= ts and te <= e) for s, e in windows]
    return [int((ts <= s and e <= te) or 2 * max(0, min(e, te) - max(s, ts)) >= e - s) for s, e in windows]


class TrainingExamples(NamedTuple):
    texts: list[str]
    labels: list[int]
    excluded: list[str]  # ids: long positives without a reliable span, left out of training (PREREG)
    uncovered: list[str]  # ids: long positives that no chunk contains, so every chunk is labelled 0 (diagnostic)


def training_examples(rows: Iterable[dict], tokenizer, max_tokens: int = MAX_TOKENS,
                      stride: int = STRIDE) -> TrainingExamples:
    """Model inputs and labels for training (PREREG "Long texts"). A frame that fits one window is one example with
    its row's label, whatever its span. A long frame is chunked: a negative's chunks are all 0; a positive's chunks
    follow `_chunk_labels` over its injected span. A long positive without a reliable span (none, one flagged
    `provenance.span_unreliable`, or one covering no token) is excluded and its id listed in `excluded`; a long
    positive whose span no window contains (a span narrower than a window can straddle every window edge) keeps its
    all-0 chunk labels and its id is listed in `uncovered`."""
    texts, labels, excluded, uncovered = [], [], [], []
    for row in rows:
        frame = render_frame(row)
        offsets, windows, width = _windows(frame, tokenizer, max_tokens, stride)
        label = int(row["label"])
        if len(windows) == 1:
            texts.append(frame)
            labels.append(label)
            continue
        chunk_labels = [0] * len(windows)
        if label:
            span = _reliable_span(row)
            offset = len(frame) - len(row["text"])  # the text closes the frame
            tokens = None if span is None else _span_tokens(offsets, span[0] + offset, span[1] + offset)
            if tokens is None:
                excluded.append(row["id"])
                continue
            chunk_labels = _chunk_labels(windows, tokens, width)
            if not any(chunk_labels):
                uncovered.append(row["id"])
        texts.extend(frame[a:b] for a, b in _char_bounds(frame, offsets, windows))
        labels.extend(chunk_labels)
    return TrainingExamples(texts, labels, excluded, uncovered)


# ---------------------------------------------------------------- embeddings


def bge_embedder(model_name: str = EMBED_MODEL, *, max_seq_length: int = MAX_TOKENS, batch_size: int = BATCH_SIZE,
                 seed: int = SEED) -> tuple[EmbedFn, object]:
    """(embed_fn, tokenizer) for the frozen local bge-small on CPU: normalized float32 vectors. Offline only: the
    offline variables are set for this process before transformers can be imported (tests scope them with
    monkeypatch), and the model loads with local_files_only."""
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
    """Memoizes an embed_fn in memory and, given a directory, on disk as `<sha256(input)>.npy`. The directory is the
    caller's key for the embedder: use `embedding_cache_dir` so another model never shares it."""

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
    coefficients so a loaded model scores bit-for-bit like the fitted one.

    Without `embed_fn` the local bge-small and its tokenizer are loaded on first use and embeddings are cached under
    `DEFAULT_CACHE` (`.fusion/detector-cache/<model>-seq256/` at the repository root) unless `cache_dir` says
    otherwise. An injected `embed_fn` must come with its `tokenizer` (chunking is part of the registered protocol)
    unless `allow_unchunked=True` scores whole frames on purpose; only an explicit `cache_dir` is used for it, and
    meta.json names it `embedder_name` (default "injected"; the LOSO driver passes EMBED_MODEL for the bge-small it
    loaded itself). `threshold` is the operating threshold chosen by the caller (saved with the model)."""

    def __init__(self, embed_fn: EmbedFn | None = None, tokenizer=None, *, cache_dir=_DEFAULT,
                 max_tokens: int = MAX_TOKENS, stride: int = STRIDE, seed: int = SEED,
                 allow_unchunked: bool = False, embedder_name: str | None = None):
        if embed_fn is not None and tokenizer is None and not allow_unchunked:
            raise ValueError("an injected embed_fn needs its tokenizer to cut 256-token windows (PREREG \"Long "
                             "texts\"): pass tokenizer=..., or allow_unchunked=True to score whole frames")
        self._embed_fn, self._tokenizer, self._cache_dir = embed_fn, tokenizer, cache_dir
        self._embedder: CachedEmbedder | None = embed_fn if isinstance(embed_fn, CachedEmbedder) else None
        self._embedder_name = embedder_name
        self.max_tokens, self.stride, self.seed = max_tokens, stride, seed
        self.allow_unchunked = allow_unchunked
        self.coef: np.ndarray | None = None
        self.intercept = 0.0
        self.threshold: float | None = None
        self.n_train = 0

    @property
    def embedder_name(self) -> str:
        """EMBED_MODEL when this model loads bge-small itself; otherwise what the caller named it, or "injected"."""
        return EMBED_MODEL if self._embed_fn is None else (self._embedder_name or INJECTED)

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        if self._embedder is None:
            fn, cache = self._embed_fn, self._cache_dir
            if fn is None:
                fn, tokenizer = bge_embedder(seed=self.seed)
                if self._tokenizer is None:
                    self._tokenizer = tokenizer
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
        """Each frame's score: the max probability over its chunks (the whole frame only with allow_unchunked and
        no tokenizer)."""
        tok = self.tokenizer
        chunks = [[f] if tok is None else chunk_frame(f, tok, self.max_tokens, self.stride) for f in frames]
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
        real = self.embedder_name == EMBED_MODEL
        meta = {"embedder": self.embedder_name, "normalize_embeddings": True if real else None,
                "max_seq_length": MAX_TOKENS if real else None,
                "max_tokens": self.max_tokens, "stride": self.stride, "intercept": self.intercept,
                "threshold": _encode_float(self.threshold), "n_train": self.n_train, "seed": self.seed,
                "classifier": "sklearn LogisticRegression(class_weight='balanced', max_iter=1000)"}
        (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")

    @classmethod
    def load(cls, directory: str | os.PathLike, embed_fn: EmbedFn | None = None, tokenizer=None, *,
             cache_dir=_DEFAULT, allow_unchunked: bool = False,
             embedder_name: str | None = None) -> EmbeddingLogistic:
        d = pathlib.Path(directory)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        model = cls(embed_fn, tokenizer, cache_dir=cache_dir, max_tokens=meta["max_tokens"], stride=meta["stride"],
                    seed=meta["seed"], allow_unchunked=allow_unchunked, embedder_name=embedder_name)
        model.coef = np.load(d / "coef.npy")
        model.intercept = float(meta["intercept"])
        model.threshold = None if meta["threshold"] is None else float(meta["threshold"])
        model.n_train = meta["n_train"]
        return model
