"""The tool-result injection detector as a guard callable (dev-only; PREREG_detector_v1.md).

`load_detector` loads the all-sources `EmbeddingLogistic` that scripts/detector_train.py saves to `<models_dir>/all/`
and returns `score(text) -> probability`: the raw untrusted text in the registered frame with no request or tool, max
over its 256-token chunks. `Guardrail(detector=score)` logs it as an observe-only event; it never changes a decision.
Without an injected embedder, bge-small loads on the first score (sentence-transformers is never imported here), and
embeddings are memoized in memory only. Shipping the weights with the runtime is not done here.
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Callable

from fusion_first.validate.detector_data import NONE, render_frame
from fusion_first.validate.detector_systems import DEFAULT_MODELS, EmbeddingLogistic, EmbedFn


def load_detector(models_dir: str | os.PathLike = DEFAULT_MODELS, *, embed_fn: EmbedFn | None = None, tokenizer=None,
                  embedder_name: str | None = None) -> Callable[[str], float]:
    """The scoring callable over `<models_dir>/all/`. An injected `embed_fn` needs its `tokenizer` (chunking is part
    of the registered protocol). Raises ValueError when the saved model names another embedder than the one scoring."""
    path = pathlib.Path(models_dir) / "all"
    model = EmbeddingLogistic.load(path, embed_fn, tokenizer, cache_dir=None, embedder_name=embedder_name)
    saved = json.loads((path / "meta.json").read_text(encoding="utf-8"))["embedder"]
    if saved != model.embedder_name:
        raise ValueError(f"{path} was trained with embedder {saved!r}; scoring with {model.embedder_name!r} "
                         "would not reproduce it")

    def score(text: str) -> float:
        return model.scores([render_frame({"request": NONE, "tool": NONE, "text": text})])[0]

    return score
