"""OR-Bench (over-refusal benchmark): toxic prompts and "hard" prompts that look unsafe but are not.

``or-bench-toxic.csv`` rows are unsafe; ``or-bench-hard-1k.csv`` rows are safe. The labels are the benchmark's own
and come from a panel of models, not from people. Upstream rows carry no index, so ids are
``orbench:<toxic|hard>:<row number in file order, from 1, zero-padded>``.
"""

from __future__ import annotations

import csv
import pathlib

NAME = "orbench"
URL = "https://huggingface.co/datasets/bench-llm/or-bench"
LICENSE = "CC-BY-4.0"
NOTE = ("Over-refusal benchmark: or-bench-toxic rows are unsafe; or-bench-hard-1k rows are safe prompts written to "
        "look unsafe. Labels come from a panel of models, not people.")
FILES = {"or-bench-toxic.csv": "toxic", "or-bench-hard-1k.csv": "hard"}
_COLUMNS = ("prompt", "category")


def load_orbench(raw_dir: pathlib.Path) -> list[dict]:
    # Lazy: the package __init__ imports this module.
    from fusion_first.validate.importers import existing_files

    found = existing_files(raw_dir, list(FILES), NAME)
    if len(found) != len(FILES):
        missing = sorted(set(FILES) - {p.name for p in found})
        raise FileNotFoundError(f"{NAME}: missing {missing} in {raw_dir} (the toxic and the hard file are a pair)")
    rows: list[dict] = []
    for path in found:
        split = FILES[path.name]
        # utf-8-sig tolerates a BOM; newline="" lets csv handle quoted fields with embedded newlines.
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in _COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{NAME} {path.name}: missing columns {missing}")
            for n, rec in enumerate(reader, start=1):
                prompt = rec["prompt"] or ""
                if not prompt.strip():
                    raise ValueError(f"{NAME} {path.name} row {n}: empty prompt")
                rows.append(
                    {
                        "id": f"{NAME}:{split}:{n:04d}",
                        "source": f"external:{NAME}@{path.name}",
                        "license": LICENSE,
                        "prompt": prompt,
                        "safe": split == "hard",
                        "label": "safe" if split == "hard" else "unsafe",
                        "category": rec["category"] or "",
                    }
                )
    return rows
