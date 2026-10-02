"""deepset/prompt-injections: benign vs prompt-injection text (English + German), label 0/1.

Ids are positional per split file, stable because the raw files are pinned by sha256 in SOURCES.yaml.
"""

from __future__ import annotations

import pathlib

NAME = "deepset"
URL = "https://huggingface.co/datasets/deepset/prompt-injections"
LICENSE = "Apache-2.0"
# The HF card's top-level license (its dataset_info block also says cc-by-4.0).
NOTE = (
    "Binary label: 1 = prompt injection, 0 = benign. HF card license is apache-2.0 (its "
    "dataset_info block also lists cc-by-4.0; both are allowlisted)."
)
SPLITS = ("train", "test")


def load_deepset(raw_dir: pathlib.Path) -> list[dict]:
    """Normalize ``{train,test}.parquet`` (columns ``text``, ``label``) into rows."""
    # Lazy: the package __init__ imports this module.
    from fusion_first.validate.importers import existing_files, read_parquet_records

    rows: list[dict] = []
    for path in existing_files(raw_dir, [f"{s}.parquet" for s in SPLITS], NAME):
        split = path.stem
        for i, rec in enumerate(read_parquet_records(path)):
            text, label = rec.get("text"), rec.get("label")
            if not isinstance(text, str):
                raise ValueError(f"{NAME} {path.name} row {i}: text must be a string, got {text!r}")
            # A True/False label (bool is an int subclass) means the schema drifted.
            if isinstance(label, bool) or not isinstance(label, int) or label not in (0, 1):
                raise ValueError(f"{NAME} {path.name} row {i}: label must be 0 or 1, got {label!r}")
            rows.append(
                {
                    "id": f"{NAME}:{split}:{i:04d}",
                    "source": f"external:{NAME}@{path.name}",
                    "license": LICENSE,
                    "split": split,
                    "text": text,
                    "label": label,
                    "injection": label == 1,
                }
            )
    return rows
