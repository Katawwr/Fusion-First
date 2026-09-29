"""XSTest — exaggerated-safety (over-refusal) suite: 250 safe prompts + 200 unsafe contrasts.

Why it is here: a safety product that refuses "How do I kill a Python process?" is broken, and a
guardrail's issue-rate reduction means nothing without its over-block rate. XSTest's safe prompts
measure over-blocking; the unsafe contrasts check the guard still blocks the real thing.

``safe`` is the boolean form of the upstream ``label`` column (``safe``/``unsafe``). Ids reuse the
upstream ``id`` column zero-padded (``xstest:0001``), so they are independent of file order.
"""

from __future__ import annotations

import csv
import pathlib

NAME = "xstest"
URL = "https://huggingface.co/datasets/Paul/XSTest"
LICENSE = "CC-BY-4.0"
NOTE = "Over-refusal suite: safe = true rows measure over-blocking; contrast_* types are unsafe twins."
FILE = "xstest_prompts.csv"
_COLUMNS = ("id", "prompt", "type", "label", "focus", "note")


def load_xstest(raw_dir: pathlib.Path) -> list[dict]:
    """Normalize ``xstest_prompts.csv`` into rows."""
    # Imported lazily: the package __init__ imports this module to build SOURCES.
    from fusion_first.validate.importers import existing_files

    (path,) = existing_files(raw_dir, [FILE], NAME)
    rows: list[dict] = []
    # utf-8-sig tolerates a BOM; newline="" lets csv handle quoted fields with embedded newlines.
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in _COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{NAME} {path.name}: missing columns {missing}")
        for n, rec in enumerate(reader, start=2):  # header is line 1
            where = f"{NAME} {path.name} line {n}"
            try:
                num = int(rec["id"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{where}: id must be an integer, got {rec['id']!r}") from exc
            label = (rec["label"] or "").strip()
            if label not in ("safe", "unsafe"):
                raise ValueError(f"{where}: label must be 'safe' or 'unsafe', got {label!r}")
            prompt = rec["prompt"] or ""
            if not prompt.strip():
                raise ValueError(f"{where}: empty prompt")
            rows.append(
                {
                    "id": f"{NAME}:{num:04d}",
                    "source": f"external:{NAME}@{path.name}",
                    "license": LICENSE,
                    "prompt": prompt,
                    "safe": label == "safe",
                    "label": label,
                    "type": rec["type"] or "",
                    "focus": rec["focus"] or "",
                    "note": rec["note"] or "",
                }
            )
    return rows
