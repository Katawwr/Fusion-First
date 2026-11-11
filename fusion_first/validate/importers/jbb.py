"""JBB-Behaviors (JailbreakBench): 100 harmful behaviours and 100 benign twins on the same topics.

``Goal`` is the prompt. ``Target`` (an affirmative reply to the goal) is not imported: nothing here needs it.
Ids are ``jbb:<harmful|benign>:<upstream Index, zero-padded>``.
"""

from __future__ import annotations

import csv
import pathlib

NAME = "jbb"
URL = "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors"
LICENSE = "MIT"
NOTE = ("Harmful behaviours and their benign twins (same topic, harmless request). Goal is the prompt; Target is "
        "not imported.")
FILES = {"harmful-behaviors.csv": "harmful", "benign-behaviors.csv": "benign"}
_COLUMNS = ("Index", "Goal", "Behavior", "Category", "Source")


def load_jbb(raw_dir: pathlib.Path) -> list[dict]:
    # Lazy: the package __init__ imports this module.
    from fusion_first.validate.importers import existing_files

    found = existing_files(raw_dir, list(FILES), NAME)
    if len(found) != len(FILES):
        missing = sorted(set(FILES) - {p.name for p in found})
        raise FileNotFoundError(f"{NAME}: missing {missing} in {raw_dir} (the harmful and the benign file are a pair)")
    rows: list[dict] = []
    for path in found:
        split = FILES[path.name]
        # utf-8-sig tolerates a BOM; newline="" lets csv handle quoted fields with embedded newlines.
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in _COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{NAME} {path.name}: missing columns {missing}")
            for n, rec in enumerate(reader, start=2):  # header is line 1
                where = f"{NAME} {path.name} line {n}"
                try:
                    num = int(rec["Index"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{where}: Index must be an integer, got {rec['Index']!r}") from exc
                prompt = rec["Goal"] or ""
                if not prompt.strip():
                    raise ValueError(f"{where}: empty Goal")
                rows.append(
                    {
                        "id": f"{NAME}:{split}:{num:04d}",
                        "source": f"external:{NAME}@{path.name}",
                        "license": LICENSE,
                        "prompt": prompt,
                        "safe": split == "benign",
                        "label": "safe" if split == "benign" else "unsafe",
                        "behavior": rec["Behavior"] or "",
                        "category": rec["Category"] or "",
                        "origin": rec["Source"] or "",
                    }
                )
    return rows
