"""Lakera/gandalf_ignore_instructions — real "ignore your instructions" attempts from the Gandalf game.

Why it is here: every row is a genuine, human-written injection attempt, so it measures RECALL of the
injection judge/guard on in-the-wild phrasing. It has NO benign negatives — never compute precision
or a false-positive rate from this source alone (pair it with deepset's label-0 rows).

``similarity`` is the upstream embedding similarity to "Ignore all previous instructions", kept so
consumers can stratify by how paraphrased an attack is. Ids are positional per split file and pinned
by the raw sha256 in SOURCES.yaml.
"""

from __future__ import annotations

import math
import pathlib

NAME = "gandalf"
URL = "https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions"
LICENSE = "MIT"
NOTE = "Every row is an injection attempt (label 1); no benign negatives — recall only."
SPLITS = ("train", "validation", "test")


def load_gandalf(raw_dir: pathlib.Path) -> list[dict]:
    """Normalize ``{train,validation,test}.parquet`` (columns ``text``, ``similarity``) into rows."""
    # Imported lazily: the package __init__ imports this module to build SOURCES.
    from fusion.validate.importers import existing_files, read_parquet_records

    rows: list[dict] = []
    for path in existing_files(raw_dir, [f"{s}.parquet" for s in SPLITS], NAME):
        split = path.stem
        for i, rec in enumerate(read_parquet_records(path)):
            text, sim = rec.get("text"), rec.get("similarity")
            if not isinstance(text, str):
                raise ValueError(f"{NAME} {path.name} row {i}: text must be a string, got {text!r}")
            if isinstance(sim, bool) or not isinstance(sim, int | float) or not math.isfinite(sim):
                raise ValueError(f"{NAME} {path.name} row {i}: bad similarity {sim!r}")
            rows.append(
                {
                    "id": f"{NAME}:{split}:{i:04d}",
                    "source": f"external:{NAME}@{path.name}",
                    "license": LICENSE,
                    "split": split,
                    "text": text,
                    "similarity": float(sim),
                    "label": 1,
                    "injection": True,
                }
            )
    return rows
