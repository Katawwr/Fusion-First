"""StrongREJECT: forbidden prompts written or curated to be specific, answerable and refused by major models.

Every row is unsafe (there is no benign half). ``forbidden_prompt`` is the prompt; ``source`` says where the authors
took it from (most are their own, the rest from AdvBench, DAN and others) and is kept as ``upstream_source``.
Upstream rows carry no index, so ids are ``strongreject:<row number in file order, from 1, zero-padded>``.
"""

from __future__ import annotations

import csv
import pathlib

NAME = "strongreject"
URL = "https://github.com/alexandrasouly/strongreject"
LICENSE = "MIT"
NOTE = ("Forbidden prompts only, every row unsafe; no benign half. upstream_source names the set each prompt was "
        "taken from (some are in AdvBench, which other imported sets also draw on).")
FILE = "strongreject_dataset.csv"
_COLUMNS = ("category", "source", "forbidden_prompt")


def load_strongreject(raw_dir: pathlib.Path) -> list[dict]:
    # Lazy: the package __init__ imports this module.
    from fusion_first.validate.importers import existing_files

    found = existing_files(raw_dir, [FILE], NAME)
    if not found:
        raise FileNotFoundError(f"{NAME}: missing {FILE} in {raw_dir}")
    rows: list[dict] = []
    # utf-8-sig tolerates a BOM; newline="" lets csv handle quoted fields with embedded newlines.
    with found[0].open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in _COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{NAME} {FILE}: missing columns {missing}")
        for n, rec in enumerate(reader, start=1):
            prompt = rec["forbidden_prompt"] or ""
            if not prompt.strip():
                raise ValueError(f"{NAME} {FILE} row {n}: empty prompt")
            rows.append(
                {
                    "id": f"{NAME}:{n:04d}",
                    "source": f"external:{NAME}@{FILE}",
                    "license": LICENSE,
                    "prompt": prompt,
                    "safe": False,
                    "label": "unsafe",
                    "category": rec["category"] or "",
                    "upstream_source": rec["source"] or "",
                }
            )
    return rows
